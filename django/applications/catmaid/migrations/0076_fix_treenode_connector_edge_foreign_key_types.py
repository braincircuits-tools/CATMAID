from django.db import migrations


forward = """
    BEGIN;

    ALTER TABLE treenode_connector_edge RENAME TO treenode_connector_edge_old;
    ALTER TABLE connector_geom RENAME TO connector_geom_old;

    -- Create new version of the treenode_connector_edge and the connector_geom
    -- tables which uses the bigint data type for its ID. All other constraints
    -- will be added after the data is copied.
    CREATE TABLE treenode_connector_edge (
        id  bigint PRIMARY KEY NOT NULL,
        project_id integer NOT NULL,
        edge geometry(LinestringZ) NOT NULL
    );
    CREATE TABLE connector_geom (
        id  bigint PRIMARY KEY NOT NULL,
        project_id integer NOT NULL,
        geom geometry(PointZ) NOT NULL
    );

    INSERT INTO treenode_connector_edge (id, project_id, edge)
    SELECT id, project_id, edge FROM treenode_connector_edge_old;

    INSERT INTO connector_geom (id, project_id, geom)
    SELECT id, project_id, geom FROM connector_geom_old;

    DROP TABLE treenode_connector_edge_old;
    DROP TABLE connector_geom_old;

    COMMIT;
"""


backward = """
    BEGIN;

    ALTER TABLE treenode_connector_edge RENAME TO treenode_connector_edge_old;

    -- Create old version of the treenode_connector_edge and the connector_geom
    -- tables which uses the bigint data type for its ID. All other constraints
    -- will be added after the data is copied.
    CREATE TABLE treenode_connector_edge (
        id  integer PRIMARY KEY NOT NULL,
        project_id integer NOT NULL,
        edge geometry(LinestringZ) NOT NULL
    );
    CREATE TABLE connector_geom (
        id  integer PRIMARY KEY NOT NULL,
        project_id integer NOT NULL,
        geom geometry(PointZ) NOT NULL
    );

    INSERT INTO treenode_connector_edge (id, project_id, edge)
    SELECT id, project_id, edge FROM treenode_connector_edge_old;

    INSERT INTO connector_geom (id, project_id, geom)
    SELECT id, project_id, geom FROM connector_geom_old;

    DROP TABLE treenode_connector_edge_old;
    DROP TABLE connector_geom_old;

    COMMIT;
"""

create_indices_and_constraints = """
    ALTER TABLE treenode_connector_edge
        ADD CONSTRAINT treenode_connector_edge_id_fkey FOREIGN KEY (id)
        REFERENCES treenode_connector_edge (id) DEFERRABLE INITIALLY DEFERRED;
    ALTER TABLE treenode_connector_edge
        ADD CONSTRAINT treenode_connector_edge_project_id_fkey FOREIGN KEY (project_id)
        REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED;

    ALTER TABLE connector_geom
        ADD CONSTRAINT connector_geom_id_fkey FOREIGN KEY (id)
        REFERENCES connector (id) DEFERRABLE INITIALLY DEFERRED;
    ALTER TABLE connector_geom
        ADD CONSTRAINT connector_geom_project_id_fkey FOREIGN KEY (project_id)
        REFERENCES project (id) DEFERRABLE INITIALLY DEFERRED;

    CREATE INDEX treenode_connector_edge_2d_gist ON treenode_connector_edge
        USING gist (edge);
    CREATE INDEX treenode_connector_edge_gix ON treenode_connector_edge
        USING gist (edge gist_geometry_ops_nd);
    CREATE INDEX treenode_connector_edge_project_index ON treenode_connector_edge
        USING btree (project_id);
    CREATE INDEX treenode_connector_edge_z_range_gist ON treenode_connector_edge
        USING gist (floatrange(st_zmin(edge::box3d), st_zmax(edge::box3d), '[]'::text));

    CREATE INDEX connector_geom_2d_gist ON connector_geom
        USING gist (geom);
    CREATE INDEX connector_geom_gix ON connector_geom
        USING gist (geom gist_geometry_ops_nd);
    CREATE INDEX connector_geom_project_index ON connector_geom
        USING btree (project_id);
    CREATE INDEX connector_geom_z_range_gist ON connector_geom
        USING gist (floatrange(st_zmin(geom::box3d), st_zmax(geom::box3d), '[]'::text));
"""

db_maintenance = """
    VACUUM ANALYZE;
"""


class Migration(migrations.Migration):
    """This migration rewrites the tables treenode_connector_edge and
    connector_geom. because their references to the tables treenode_connector
    and connector are wrong and need to be updated. Up to this migration the id
    column was of type int, but since it references the treenode_edge id column
    (and the connector id column), it should follow its type, which is bigint.
    This is updated by this migration by creating a new table. This has the
    benefit that cleaning up the old table is easier and doesn't need a VACUUM
    FULL run.
    """

    dependencies = [
        ('catmaid', '0075_make_concept_ids_64_bit'),
    ]

    operations = [
        migrations.RunSQL(migrations.RunSQL.noop, db_maintenance),
        migrations.RunSQL(migrations.RunSQL.noop, create_indices_and_constraints),
        migrations.RunSQL(forward, backward),
        migrations.RunSQL(create_indices_and_constraints, migrations.RunSQL.noop),
        migrations.RunSQL(db_maintenance, migrations.RunSQL.noop),
    ]
