// /account/teacher/: Teacher access (Gaps "Teacher access fixed", Phone "Phone privacy and teacher"): ask once (POST
// me/teacher/) with the school, district and subject; then the request's state from GET me/teacher/ (404 until asked):
// being checked, or verified. Nothing more: there is no view of students (G14).
import { PageHead, Problem } from "@/components/account/parts";
import { TeacherAccess } from "@/components/account/profile-forms";
import { getSubjects, settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Teacher access",
  path: "/account/teacher/",
  description: "Ask for teacher access to ExamLeaf by telling us where you teach.",
  noindex: true,
});

export default async function TeacherPage() {
  const path = "/account/teacher/";
  const [teacher, subjects] = await Promise.all([
    settle(unwrap(serverApi.GET("/api/v1/me/teacher/", await personalFetch())), path),
    getSubjects().catch(() => []),
  ]);
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
      <div className="max-w-[30rem]">
        <TeacherAccess
          request={teacher instanceof ApiError ? null : teacher}
          subjects={[...new Set(subjects.map((subject) => subject.name))]}
        />
      </div>
    </>
  );
}
