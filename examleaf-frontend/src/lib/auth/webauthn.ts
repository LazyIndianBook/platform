// The browser's passkey prompt for allauth.headless: its options come as JSON (base64url for the binary fields) and
// it wants the credential back as JSON. Native parse/toJSON where the browser has them (Chrome 129+, Safari 18.4+,
// Firefox 119+), a small conversion for the others (older Android WebViews).
type RequestOptionsJSON = {
  challenge: string;
  allowCredentials?: { id: string; type: string; transports?: string[] }[];
  [key: string]: unknown;
};

const toBuffer = (value: string) => {
  const base64 = value
    .replace(/-/g, "+")
    .replace(/_/g, "/")
    .padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(base64), (char) => char.charCodeAt(0)).buffer;
};

const toBase64url = (buffer: ArrayBuffer | null) =>
  buffer === null
    ? null
    : btoa(String.fromCharCode(...new Uint8Array(buffer)))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");

type NativeParse = { parseRequestOptionsFromJSON?: (json: RequestOptionsJSON) => PublicKeyCredentialRequestOptions };

export function decodeRequestOptions(json: RequestOptionsJSON): PublicKeyCredentialRequestOptions {
  const native = (globalThis.PublicKeyCredential as unknown as NativeParse | undefined)?.parseRequestOptionsFromJSON;
  if (native) return native(json);
  return {
    ...(json as unknown as PublicKeyCredentialRequestOptions),
    challenge: toBuffer(json.challenge),
    allowCredentials: json.allowCredentials?.map((item) => ({
      ...item,
      type: "public-key" as const,
      id: toBuffer(item.id),
      transports: item.transports as AuthenticatorTransport[] | undefined,
    })),
  };
}

export function encodeCredential(credential: PublicKeyCredential): unknown {
  const withJSON = credential as PublicKeyCredential & { toJSON?: () => unknown };
  if (typeof withJSON.toJSON === "function") return withJSON.toJSON();
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: toBase64url(response.clientDataJSON),
      authenticatorData: toBase64url(response.authenticatorData),
      signature: toBase64url(response.signature),
      userHandle: toBase64url(response.userHandle),
    },
  };
}

/** Shows the browser's passkey prompt; throws DOMException NotAllowedError when the visitor cancels it. */
export async function getCredential(requestOptions: unknown): Promise<unknown> {
  const { publicKey } = requestOptions as { publicKey: RequestOptionsJSON };
  if (!globalThis.PublicKeyCredential) throw new DOMException("Passkeys are not supported here", "NotSupportedError");
  const credential = await navigator.credentials.get({ publicKey: decodeRequestOptions(publicKey) });
  if (!credential) throw new DOMException("No passkey was chosen", "NotAllowedError");
  return encodeCredential(credential as PublicKeyCredential);
}
