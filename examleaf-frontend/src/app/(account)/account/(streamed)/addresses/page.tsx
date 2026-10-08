// /account/addresses/: the saved delivery addresses (Django's my_account.html #details and shop/address_form.html):
// GET addresses/, then the address book's island to add, change and delete them.
import { AddressBook } from "@/components/account/address-book";
import { ConsentPending, PageHead, Problem } from "@/components/account/parts";
import { Card, CardContent } from "@/components/ui/card";
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
  const head = <PageHead title="Addresses" lead="Where your books go. Checkout lists them, the default one first." />;
  if (list instanceof ApiError) {
    return (
      <>
        {head}
        <Problem error={list} what="Your addresses" retry={path} />
      </>
    );
  }
  return (
    <>
      {head}
      {!(me instanceof ApiError) && me.consent_pending ? (
        <ConsentPending what="you can save addresses but not order books" />
      ) : null}
      <Card>
        <CardContent>
          <AddressBook addresses={list.results} />
        </CardContent>
      </Card>
    </>
  );
}
