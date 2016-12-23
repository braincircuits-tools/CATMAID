# -*- coding: utf-8 -*-
# Generated by Django 1.9.11 on 2016-12-19 00:02
from __future__ import unicode_literals

import os
import logging

import django.contrib.postgres.fields.jsonb
from django.conf import settings
from django.db import migrations, models

from catmaid.apps import get_system_user
from catmaid.control.volume import get_volume_instance

from contextlib import closing

# Get an instance of a logger
logger = logging.getLogger(__name__)

def get_mesh(project_id, stack_id):
    """Return a triangle mesh for a project/stack combination or None.
    """
    d = {}
    patterns = (
        ('%s_%s.hdf', (project_id, stack_id)),
        ('%s.hdf', (project_id,))
    )

    filename = None
    for p in patterns:
        test_filename = os.path.join(settings.HDF5_STORAGE_PATH, p[0] % p[1])
        if os.path.exists(test_filename):
            filename = test_filename
            break

    if not filename:
        return None

    # Importing only if a mesh was found might make it easier to remove the HDF5
    # dependency at some point. This shouldn't be too much overhead for the few
    # function calls we expect.
    try:
        import h5py
    except ImportError, e:
        logger.warning("CATMAID was unable to import the h5py library. "
                "This library is needed to migrate found HDF5 files to "
                "volumes, please install it (e.g. using pip install h5py).")
        raise 

    with closing(h5py.File(filename, 'r')) as hfile:
        meshnames = hfile['meshes'].keys()
        for name in meshnames:
            vertlist = hfile['meshes'][name]['vertices'].value.tolist()
            facelist = hfile['meshes'][name]['faces'].value.tolist()
            d[str(name)] = {
                'vertices': vertlist,
                'faces': facelist
            }

    return d

def import_meshes(apps, schema_editor):
    """Look for HDF5 meshes in the settings specified HDF5 folder. If any are
    found, import them as PostGIS volumes.
    """

    Project = apps.get_model("catmaid", "Project")
    Stack = apps.get_model("catmaid", "Stack")

    user = None

    for project in Project.objects.all():
        for stack in Stack.objects.all():
            meshes = get_mesh(project.id, stack.id)
            if not meshes:
                continue

            if not user:
                # Lazy load system user
                user = get_system_user()

            # The returned dictionary maps mesh names to a mesh representation
            for mesh_name, mesh_data in meshes.iteritems():
                vertices = []
                input_vertices = mesh_data['vertices']
                i = 0
                while i < len(input_vertices):
                    vertices.append([
                        input_vertices[i],
                        input_vertices[i+1],
                        input_vertices[i+2]
                    ])
                    i = i + 3
                triangles = []
                input_faces = mesh_data['faces']
                i = 0
                while i < len(input_faces):
                    face_type = input_faces[i]
                    if 0 == face_type:
                        triangles.append([
                            input_faces[i+1],
                            input_faces[i+2],
                            input_faces[i+3]
                        ])
                        i = i + 4
                    elif 1 == face_type:
                        triangles.append([
                            input_faces[i+1],
                            input_faces[i+2],
                            input_faces[i+3]
                        ])
                        triangles.append([
                            input_faces[i+3],
                            input_faces[i+4],
                            input_faces[i+1]
                        ])
                        i = i + 5
                    else:
                        raise ValueError("Can't migrate HDF5 mesh {}_{}.hdf, "
                                "because it contains faces different from "
                                "triangles or quads (type {}).".format(
                                project.id, stack.id, i))
                params = {
                    'type': 'trimesh',
                    'title': mesh_name,
                    'comment': 'Imported HDF5 mesh ' +
                        '(project: {} stack: {})'.format(project.id, stack.id),
                    'mesh': [
                        vertices,
                        triangles
                    ]
                }
                instance = get_volume_instance(project.id, user.id, params)
                volume_id = instance.save()

class Migration(migrations.Migration):

    dependencies = [
        ('catmaid', '0015_fix_history_views'),
    ]

    operations = [
        migrations.RunPython(import_meshes, migrations.RunPython.noop)
    ]
