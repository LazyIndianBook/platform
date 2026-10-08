// /account/addresses/: the saved delivery addresses (Account artboard "Details and addresses", Phone "Phone addresses
// and security"): GET addresses/, then the address book's island to add, change, make default and delete them.
import { AddressBook } from "@/components/account/address-book";
import { ConsentPending, PageHead, Problem } from "@/components/account/parts";
import { getMe, settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({ title: "Addresses", path: "/account/addresses/", noindex: true });

export default async function AddressesPage() {
  const path = "/account/addresses/";
  const [list, me] = await Promise.all([
    settle(
      unwrap(
        serverApi.GET("/api/v1/addresses/", { params: { query: { page_size: 200 } }, ...(await personalFetch()) }),
      ),
      path,
    ),
    settle(getMe(), path),
  ]);
  if (list instanceof ApiError) {
    return (
      <>
        <PageHead title="Addresses" />
        <Problem error={list} what="Your addresses" retry={path} />
      </>
    );
  }
  return (
    <AddressBook addresses={list.results}>
      {!(me instanceof ApiError) && me.consent_pending ? (
        <ConsentPending what="you can save addresses but not order books" contact={me.parent_contact} />
      ) : null}
    </AddressBook>
  );
}
