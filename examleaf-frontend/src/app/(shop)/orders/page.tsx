// /orders/: the signed-in customer's orders live at /account/orders/ (Django's address, kept); a visitor finds an
// order by its emailed link, or asks for it again.
import { redirect } from "next/navigation";

import { getSessionUser } from "@/lib/auth/session";

export default async function Orders() {
  redirect((await getSessionUser()) ? "/account/orders/" : "/orders/lookup/");
}
