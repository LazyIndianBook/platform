"""The audit log is append-only on PostgreSQL (research 3.3): a trigger refuses UPDATE, DELETE and TRUNCATE on
staff_auditevent. The retention purge (staff.audit.purge, `manage.py purge_audit`) sets `examleaf.audit_maintenance`
for its own transaction first; run it as the table's owner, the role migrations run as, and give the app's own role
SELECT and INSERT only (DEPLOYMENT.md "Staff and the audit log"). Removing the trigger is DDL: it shows. SQLite
(development, tests) has no such trigger; the hash chain is checked there as everywhere."""

from django.db import migrations

CREATE = """
CREATE OR REPLACE FUNCTION staff_audit_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP <> 'UPDATE' AND current_setting('examleaf.audit_maintenance', true) = 'on' THEN
        RETURN OLD;  -- the retention purge (a TRUNCATE trigger's value is ignored); never an UPDATE
    END IF;
    RAISE EXCEPTION USING ERRCODE = 'insufficient_privilege',
        MESSAGE = 'staff_auditevent is append-only: ' || TG_OP || ' refused';  -- (no percent sign: psycopg)
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER staff_audit_no_update_delete BEFORE UPDATE OR DELETE ON staff_auditevent
    FOR EACH ROW EXECUTE FUNCTION staff_audit_append_only();
CREATE TRIGGER staff_audit_no_truncate BEFORE TRUNCATE ON staff_auditevent
    FOR EACH STATEMENT EXECUTE FUNCTION staff_audit_append_only();
"""
DROP = """
DROP TRIGGER IF EXISTS staff_audit_no_truncate ON staff_auditevent;
DROP TRIGGER IF EXISTS staff_audit_no_update_delete ON staff_auditevent;
DROP FUNCTION IF EXISTS staff_audit_append_only();
"""


def on_postgresql(sql):
    def run(apps, schema_editor):
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(sql)

    return run


class Migration(migrations.Migration):
    dependencies = [("staff", "0001_initial")]
    operations = [migrations.RunPython(on_postgresql(CREATE), on_postgresql(DROP))]
