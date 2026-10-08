// /orders/<number>/: an order's page is /account/orders/<number>/ (Django's address, kept: the API's web_url).
import { permanentRedirect } from "next/navigation";

export default async function OrderByNumber({ params }: { params: Promise<{ number: string }> }) {
  permanentRedirect(`/account/orders/${encodeURIComponent((await params).number)}/`);
}
