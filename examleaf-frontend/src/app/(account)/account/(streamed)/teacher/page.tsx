// /account/teacher/: Teacher access (Django's teacher_request.html and the line on My account): ask once (POST
// me/teacher/) with the school, district and subject; then the request's state from GET me/teacher/ (404 until asked).
import { PageHead, Problem } from "@/components/account/parts";
import { TeacherForm } from "@/components/account/profile-forms";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { formatDate } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Teacher access",
  path: "/account/teacher/",
  description: "Ask for teacher access to ExamLeaf by telling us where you teach.",
  noindex: true,
});

export default async function TeacherPage() {
  const path = "/account/teacher/";
  const teacher = await settle(unwrap(serverApi.GET("/api/v1/me/teacher/", await personalFetch())), path);
  const asked = !(teacher instanceof ApiError);
  const head = (
    <PageHead
      title="Teacher access"
      lead={
        asked
          ? undefined
          : "Tell us where you teach. We check with the school, then your account is marked as a teacher's."
      }
    />
  );
  if (teacher instanceof ApiError && teacher.status !== 404) {
    return (
      <>
        {head}
        <Problem error={teacher} what="Teacher access" retry={path} />
      </>
    );
  }
  return (
    <>
      {head}
      <Card>
        <CardContent>
          {!asked ? (
            <TeacherForm />
          ) : teacher.verified ? (
            <Alert variant="success" title="You are a verified teacher">
              <p>
                At {teacher.school_name}, {teacher.district}
                {teacher.verified_at ? `, since ${formatDate(teacher.verified_at, "long")}` : ""}.
              </p>
            </Alert>
          ) : (
            <Alert variant="info" title="We are checking your request">
              <p>
                {teacher.school_name}, {teacher.district} ({teacher.subject}), asked on{" "}
                {formatDate(teacher.created, "long")}. Once we have checked with your school, this page shows you as a
                verified teacher.
              </p>
            </Alert>
          )}
        </CardContent>
      </Card>
    </>
  );
}
