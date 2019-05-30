from django.db import migrations


forward = """
    UPDATE change_request
    SET id = nextval('concept_id_seq');

    ALTER TABLE ONLY change_request ALTER COLUMN id SET DEFAULT nextval('concept_id_seq'::regclass);

    DROP SEQUENCE change_request_id_seq;
"""

backward = """
    CREATE SEQUENCE change_request_id_seq
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;

    ALTER SEQUENCE change_request_id_seq OWNED BY change_request.id;

    ALTER TABLE ONLY change_request ALTER COLUMN id SET DEFAULT nextval('change_request_id_seq'::regclass);

    UPDATE change_request
    SET id = nextval('concept_id_seq');
"""


class Migration(migrations.Migration):
    """This removes the ID sequence the change_requests table is using and makes
    it use the regular concept ID sequence (it inherits from concept). New IDs
    will be assigned to all change requests. It is not possible to revert to the
    original IDs.
    """

    dependencies = [
        ('catmaid', '0073_make_skeleton_summary_update_more_modular'),
    ]

    operations = [
        migrations.RunSQL(forward, backward)
    ]
