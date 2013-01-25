from django import forms
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from datetime import datetime
import sys
import re
import urllib

from django.contrib.auth.models import User
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from .fields import Double3DField, Integer3DField, IntegerArrayField, RGBAField

from guardian.shortcuts import get_objects_for_user

from taggit.managers import TaggableManager

CELL_BODY_CHOICES = (
    ('u', 'Unknown'),
    ('l', 'Local'),
    ('n', 'Non-Local' ))

class UserRole(object):
    Admin = 'Admin'
    Annotate = 'Annotate'
    Browse = 'Browse'

class Project(models.Model):
    class Meta:
        db_table = "project"
        managed = True
        permissions = (
            ("can_administer", "Can administer projects"), 
            ("can_annotate", "Can annotate projects"), 
            ("can_browse", "Can browse projects")
        )
    title = models.TextField()
    public = models.BooleanField(default=True)
    stacks = models.ManyToManyField("Stack",
                                    through='ProjectStack')
    tags = TaggableManager(blank=True)
    wiki_base_url = models.TextField(null=True, blank=True)
    
    def __unicode__(self):
        return self.title

class Stack(models.Model):
    class Meta:
        db_table = "stack"
    title = models.TextField()
    dimension = Integer3DField()
    resolution = Double3DField()
    image_base = models.TextField()
    comment = models.TextField(blank=True, null=True)
    trakem2_project = models.BooleanField(default=False)
    num_zoom_levels = models.IntegerField(default=-1)
    file_extension = models.TextField(default='jpg', blank=True)
    tile_width = models.IntegerField(default=256)
    tile_height = models.IntegerField(default=256)
    tile_source_type = models.IntegerField(default=1)
    metadata = models.TextField(default='', blank=True)
    tags = TaggableManager(blank=True)

    def __unicode__(self):
        return self.title

class ProjectStack(models.Model):
    class Meta:
        db_table = "project_stack"
    project = models.ForeignKey(Project)
    stack = models.ForeignKey(Stack)
    translation = Double3DField(default=(0, 0, 0))

    def __unicode__(self):
        return self.project.title + " -- " + self.stack.title

class Overlay(models.Model):
    class Meta:
        db_table = "overlay"
    title = models.TextField()
    stack = models.ForeignKey(Stack)
    image_base = models.TextField()
    default_opacity = models.IntegerField(default=0)
    file_extension = models.TextField()
    tile_width = models.IntegerField(default=512)
    tile_height = models.IntegerField(default=512)
    tile_source_type = models.IntegerField(default=1)

class Concept(models.Model):
    class Meta:
        db_table = "concept"
    user = models.ForeignKey(User)
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    project = models.ForeignKey(Project)

class Class(models.Model):
    class Meta:
        db_table = "class"
    # Repeat the columns inherited from 'concept'
    user = models.ForeignKey(User)
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    project = models.ForeignKey(Project)
    # Now new columns:
    class_name = models.CharField(max_length=255)
    description = models.TextField()

class ConnectivityDirection:
    PRESYNAPTIC_PARTNERS = 0
    POSTSYNAPTIC_PARTNERS = 1

class ClassInstance(models.Model):
    class Meta:
        db_table = "class_instance"
    # Repeat the columns inherited from 'concept'
    user = models.ForeignKey(User)
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    project = models.ForeignKey(Project)
    # Now new columns:
    class_column = models.ForeignKey(Class, db_column="class_id") # underscore since class is a keyword
    name = models.CharField(max_length=255)

    def get_connected_neurons(self, project_id, direction, skeletons):

        if direction == ConnectivityDirection.PRESYNAPTIC_PARTNERS:
            this_to_syn = 'post'
            syn_to_con = 'pre'
        elif direction == ConnectivityDirection.POSTSYNAPTIC_PARTNERS:
            this_to_syn = 'pre'
            syn_to_con = 'post'
        else:
            raise Exception, "Unknown connectivity direction: "+str(direction)

        relations = dict((r.relation_name, r.id) for r in Relation.objects.filter(project=project_id))
        classes = dict((c.class_name, c.id) for c in Class.objects.filter(project=project_id))

        connected_skeletons_dict={}
        # Find connectivity for each skeleton and add neuron name
        for skeleton in skeletons:
            qs_tc = TreenodeConnector.objects.filter(
                project=project_id,
                skeleton=skeleton.id,
                relation=relations[this_to_syn+'synaptic_to']
            ).select_related('connector')

            # extract all connector ids
            connector_ids=[]
            for tc in qs_tc:
                connector_ids.append( tc.connector_id )
            # find all syn_to_con connections
            qs_tc = TreenodeConnector.objects.filter(
                project=project_id,
                connector__in=connector_ids,
                relation=relations[syn_to_con+'synaptic_to']
            )
            # extract all skeleton ids
            first_indirection_skeletons=[]
            for tc in qs_tc:
                first_indirection_skeletons.append( tc.skeleton_id )

            qs = ClassInstanceClassInstance.objects.filter(
                relation__relation_name='model_of',
                project=project_id,
                class_instance_a__in=first_indirection_skeletons).select_related("class_instance_b")
            neuronOfSkeleton={}
            for ele in qs:
                neuronOfSkeleton[ele.class_instance_a.id]={
                    'neuroname':ele.class_instance_b.name,
                    'neuroid':ele.class_instance_b.id
                }

            # add neurons (or rather skeletons)
            for skeleton_id in first_indirection_skeletons:

                if skeleton_id in connected_skeletons_dict:
                    # if already existing, increase count
                    connected_skeletons_dict[skeleton_id]['id__count']+=1
                else:
                    connected_skeletons_dict[skeleton_id]={
                        'id': neuronOfSkeleton[skeleton_id]['neuroid'],
                        'id__count': 1, # connectivity count
                        'skeleton_id': skeleton_id,
                        'name': '{0} / skeleton {1}'.format(neuronOfSkeleton[skeleton_id]['neuroname'], skeleton_id) }

        # sort by count
        from operator import itemgetter
        connected_skeletons = connected_skeletons_dict.values()
        result = reversed(sorted(connected_skeletons, key=itemgetter('id__count')))
        return result

    def all_neurons_upstream(self, project_id, skeletons):
        return self.get_connected_neurons(
            project_id,
            ConnectivityDirection.PRESYNAPTIC_PARTNERS, skeletons)

    def all_neurons_downstream(self, project_id, skeletons):
        return self.get_connected_neurons(
            project_id,
            ConnectivityDirection.POSTSYNAPTIC_PARTNERS, skeletons)

    def cell_body_location(self):
        qs = list(ClassInstance.objects.filter(
                class_column__class_name='cell_body_location',
                cici_via_b__relation__relation_name='has_cell_body',
                cici_via_b__class_instance_a=self))
        if len(qs) == 0:
            return 'Unknown'
        elif len(qs) == 1:
            return qs[0].name
        elif qs:
            raise Exception, "Multiple cell body locations found for neuron '%s'" % (self.name,)
    def set_cell_body_location(self, new_location):
        # FIXME: for the moment, just hardcode the user ID:
        user = User.objects.get(pk=3)
        if new_location not in [x[1] for x in CELL_BODY_CHOICES]:
            raise Exception, "Incorrect cell body location '%s'" % (new_location,)
        # Just delete the ClassInstance - ON DELETE CASCADE should deal with the rest:
        ClassInstance.objects.filter(
            cici_via_b__relation__relation_name='has_cell_body',
            cici_via_b__class_instance_a=self).delete()
        if new_location != 'Unknown':
            location = ClassInstance()
            location.name=new_location
            location.project = self.project
            location.user = user
            location.class_column = Class.objects.get(class_name='cell_body_location', project=self.project)
            location.save()
            r = Relation.objects.get(relation_name='has_cell_body', project=self.project)
            cici = ClassInstanceClassInstance()
            cici.class_instance_a = self
            cici.class_instance_b = location
            cici.relation = r
            cici.user = user
            cici.project = self.project
            cici.save()
    def lines_as_str(self):
        # FIXME: not expected to work yet
        return ', '.join([unicode(x) for x in self.lines.all()])
    def to_dict(self):
        # FIXME: not expected to work yet
        return {'id': self.id,
                'trakem2_id': self.trakem2_id,
                'lineage' : 'unknown',
                'neurotransmitters': [],
                'cell_body_location': [ self.cell_body, Neuron.cell_body_choices_dict[self.cell_body] ],
                'name': self.name}

class Relation(models.Model):
    class Meta:
        db_table = "relation"
    # Repeat the columns inherited from 'concept'
    user = models.ForeignKey(User)
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    project = models.ForeignKey(Project)
    # Now new columns:
    relation_name = models.CharField(max_length=255)
    uri = models.TextField()
    description = models.TextField()
    isreciprocal = models.BooleanField()

class RelationInstance(models.Model):
    class Meta:
        db_table = "relation_instance"
    # Repeat the columns inherited from 'concept'
    user = models.ForeignKey(User)
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    project = models.ForeignKey(Project)
    # Now new columns:
    relation = models.ForeignKey(Relation)

class ClassInstanceClassInstance(models.Model):
    class Meta:
        db_table = "class_instance_class_instance"
    # Repeat the columns inherited from 'relation_instance'
    user = models.ForeignKey(User)
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    project = models.ForeignKey(Project)
    relation = models.ForeignKey(Relation)
    # Now new columns:
    class_instance_a = models.ForeignKey(ClassInstance,
                                         related_name='cici_via_a',
                                         db_column='class_instance_a')
    class_instance_b = models.ForeignKey(ClassInstance,
                                         related_name='cici_via_b',
                                         db_column='class_instance_b')

class BrokenSlice(models.Model):
    class Meta:
        db_table = "broken_slice"
    stack = models.ForeignKey(Stack)
    index = models.IntegerField()

class ClassClass(models.Model):
    class Meta:
        db_table = "class_class"
    # Repeat the columns inherited from 'relation_instance'
    user = models.ForeignKey(User)
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    project = models.ForeignKey(Project)
    relation = models.ForeignKey(Relation)
    # Now new columns:
    class_a = models.ForeignKey(Class, related_name='classes_a',
                                db_column='class_a')
    class_b = models.ForeignKey(Class, related_name='classes_b',
                                db_column='class_b')

class Message(models.Model):
    class Meta:
        db_table = "message"
    user = models.ForeignKey(User)
    time = models.DateTimeField(default=datetime.now)
    read = models.BooleanField(default=False)
    title = models.TextField()
    text = models.TextField(default='New message', blank=True, null=True)
    action = models.TextField(blank=True, null=True)

class Settings(models.Model):
    class Meta:
        db_table = "settings"
    key = models.TextField(primary_key=True)
    value = models.TextField(null=True)


class UserFocusedManager(models.Manager):
    # TODO: should there be a parameter or separate function that allows the caller to specify read-only vs. read-write objects?
    
    def for_user(self, user):
        fullSet = super(UserFocusedManager, self).get_query_set()
        
        if user.is_superuser:
            return fullSet
        else:
            # Get the projects that the user can see.
            adminProjects = get_objects_for_user(user, 'can_administer', Project)
            print >> sys.stderr, 'user is admin for ', str(adminProjects)
            otherProjects = get_objects_for_user(user, ['can_annotate', 'can_browse'], Project, any_perm = True)
            otherProjects = [a for a in otherProjects if a not in adminProjects]
            print >> sys.stderr, 'user has access to ', str(otherProjects)
            
            # Now filter to the data to which the user has access.
            return fullSet.filter(Q(project__in = adminProjects) | (Q(project__in = otherProjects) & Q(user = user)))


class UserFocusedModel(models.Model):
    objects = UserFocusedManager()
    user = models.ForeignKey(User)
    project = models.ForeignKey(Project)
    class Meta:
        abstract = True


class Textlabel(models.Model):
    class Meta:
        db_table = "textlabel"
    type = models.CharField(max_length=32)
    text = models.TextField(default="Edit this text ...")
    colour = RGBAField(default=(1, 0.5, 0, 1))
    font_name = models.TextField(null=True)
    font_style = models.TextField(null=True)
    font_size = models.FloatField(default=32)
    project = models.ForeignKey(Project)
    scaling = models.BooleanField(default=True)
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    deleted = models.BooleanField(default=False)

class TextlabelLocation(models.Model):
    class Meta:
        db_table = "textlabel_location"
    textlabel = models.ForeignKey(Textlabel)
    location = Double3DField()
    deleted = models.BooleanField(default=False)

class Location(UserFocusedModel):
    class Meta:
        db_table = "location"
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    editor = models.ForeignKey(User, related_name='location_editor', db_column='editor_id')
    location = Double3DField()
    reviewer_id = models.IntegerField(default=-1)
    review_time = models.DateTimeField()

class Treenode(UserFocusedModel):
    class Meta:
        db_table = "treenode"
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    editor = models.ForeignKey(User, related_name='treenode_editor', db_column='editor_id')
    location = Double3DField()
    parent = models.ForeignKey('self', null=True, related_name='children')
    radius = models.FloatField()
    confidence = models.IntegerField(default=5)
    skeleton = models.ForeignKey(ClassInstance)
    reviewer_id = models.IntegerField(default=-1)
    review_time = models.DateTimeField()


class Connector(UserFocusedModel):
    class Meta:
        db_table = "connector"
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    editor = models.ForeignKey(User, related_name='connector_editor', db_column='editor_id')
    location = Double3DField()
    confidence = models.IntegerField(default=5)
    reviewer_id = models.IntegerField(default=-1)
    review_time = models.DateTimeField()


class TreenodeClassInstance(UserFocusedModel):
    class Meta:
        db_table = "treenode_class_instance"
    # Repeat the columns inherited from 'relation_instance'
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    relation = models.ForeignKey(Relation)
    # Now new columns:
    treenode = models.ForeignKey(Treenode)
    class_instance = models.ForeignKey(ClassInstance)

class ConnectorClassInstance(UserFocusedModel):
    class Meta:
        db_table = "connector_class_instance"
    # Repeat the columns inherited from 'relation_instance'
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    relation = models.ForeignKey(Relation)
    # Now new columns:
    connector = models.ForeignKey(Connector)
    class_instance = models.ForeignKey(ClassInstance)

class TreenodeConnector(UserFocusedModel):
    class Meta:
        db_table = "treenode_connector"
    # Repeat the columns inherited from 'relation_instance'
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    relation = models.ForeignKey(Relation)
    # Now new columns:
    treenode = models.ForeignKey(Treenode)
    connector = models.ForeignKey(Connector)
    skeleton = models.ForeignKey(ClassInstance)
    confidence = models.IntegerField(default=5)

# ------------------------------------------------------------------------
# Now the non-Django tables:

SORT_ORDERS_TUPLES = [ ( 'name', ('name', False, 'Neuron name') ),
                       ( 'namer', ('name', True, 'Neuron name (reversed)') ),
                       ( 'gal4', ('gal4', False, 'GAL4 lines') ),
                       ( 'gal4r', ('gal4', True, 'GAL4 lines (reversed)') ),
                       ( 'cellbody', ('cell_body', False, 'Cell body location') ),
                       ( 'cellbodyr' , ('cell_body', True, 'Cell body location (reversed)') ) ]
SORT_ORDERS_DICT = dict(SORT_ORDERS_TUPLES)
SORT_ORDERS_CHOICES = tuple((x[0],SORT_ORDERS_DICT[x[0]][2]) for x in SORT_ORDERS_TUPLES)

class NeuronSearch(forms.Form):
    search = forms.CharField(max_length=100,required=False)
    cell_body_location = forms.ChoiceField(
        choices=((('a','Any'),)+CELL_BODY_CHOICES))
    order_by = forms.ChoiceField(SORT_ORDERS_CHOICES)
    def minimal_search_path(self):
        result = ""
        parameters = [ ( 'search', '/find/', '' ),
                       ( 'order_by', '/sorted/', 'name' ),
                       ( 'cell_body_location', '/cell_body_location/', "-1" ) ]
        for p in parameters:
            if self.cleaned_data[p[0]] != p[2]:
                result += p[1] + urllib.quote(str(self.cleaned_data[p[0]]))
        return result

class ApiKey(models.Model):
    description = models.TextField()
    key = models.CharField(max_length=128)

class Log(UserFocusedModel):
    class Meta:
        db_table = "log"
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    operation_type = models.CharField(max_length=255)
    location = Double3DField()
    freetext = models.TextField()

class SkeletonlistDashboard(UserFocusedModel):
    class Meta:
        db_table = "skeletonlist_dashboard"
    shortname = models.CharField(max_length=255)
    skeleton_list = IntegerArrayField()
    description = models.TextField()

class Segments(UserFocusedModel):

    creation_time = models.DateTimeField(default=now)
    edition_time = models.DateTimeField(default=now)

    stack = models.ForeignKey(Stack)

    assembly = models.ForeignKey(ClassInstance,null=True)

    segmentid = models.IntegerField(db_index=True)
    segmenttype = models.IntegerField(db_index=True)
    origin_section = models.IntegerField(db_index=True)
    origin_slice_id = models.IntegerField(db_index=True)
    target1_section = models.IntegerField(db_index=True,null=True)
    target1_slice_id = models.IntegerField(db_index=True,null=True)
    target2_section = models.IntegerField(db_index=True,null=True)
    target2_slice_id = models.IntegerField(db_index=True,null=True)
    cost = models.FloatField()
    direction = models.BooleanField() # 0:LR if origin_section< target_section / 1:RL as boolean, otherwise

    center_distance = models.FloatField()
    set_difference = models.FloatField()
    set_difference_ratio = models.FloatField()
    aligned_set_difference = models.FloatField()
    aligned_set_difference_ratio = models.FloatField()
    size = models.FloatField()
    overlap = models.FloatField()
    overlap_ratio = models.FloatField()
    aligned_overlap = models.FloatField()
    aligned_overlap_ratio = models.FloatField()
    average_slice_distance = models.FloatField()
    max_slice_distance = models.FloatField()
    aligned_average_slice_distance = models.FloatField()
    aligned_max_slice_distance = models.FloatField()
    histogram_0 = models.FloatField()
    histogram_1 = models.FloatField()
    histogram_2 = models.FloatField()
    histogram_3 = models.FloatField()
    histogram_4 = models.FloatField()
    histogram_5 = models.FloatField()
    histogram_6 = models.FloatField()
    histogram_7 = models.FloatField()
    histogram_8 = models.FloatField()
    histogram_9 = models.FloatField()
    normalized_histogram_0 = models.FloatField()
    normalized_histogram_1 = models.FloatField()
    normalized_histogram_2 = models.FloatField()
    normalized_histogram_3 = models.FloatField()
    normalized_histogram_4 = models.FloatField()
    normalized_histogram_5 = models.FloatField()
    normalized_histogram_6 = models.FloatField()
    normalized_histogram_7 = models.FloatField()
    normalized_histogram_8 = models.FloatField()
    normalized_histogram_9 = models.FloatField()


class Slices(UserFocusedModel):

    creation_time = models.DateTimeField(default=now)
    edition_time = models.DateTimeField(default=now)
    stack = models.ForeignKey(Stack)

    assembly = models.ForeignKey(ClassInstance,null=True,db_index=True)
    sectionindex = models.IntegerField(db_index=True) # index of the section
    slice_id = models.IntegerField(db_index=True) # int id local to the section
    node_id = models.CharField(max_length=255,db_index=True) # convention: {sectionindex}_{slide_id}

    # boundingbox (in pixel coordiantes)
    min_x = models.IntegerField(db_index=True)
    min_y = models.IntegerField(db_index=True)
    max_x = models.IntegerField(db_index=True)
    max_y = models.IntegerField(db_index=True)

    center_x = models.FloatField(db_index=True)
    center_y = models.FloatField(db_index=True)
    threshold = models.FloatField()
    size = models.IntegerField(db_index=True)
    status = models.IntegerField(db_index=True, default=0)

class Drawing(UserFocusedModel):
    class Meta:
        db_table = "drawing"
    creation_time = models.DateTimeField(default=datetime.now)
    edition_time = models.DateTimeField(default=datetime.now)
    stack = models.ForeignKey(Stack)
    skeleton_id = models.IntegerField()
    z = models.IntegerField()
    component_id=models.IntegerField()
    min_x = models.IntegerField()
    min_y = models.IntegerField()
    max_x = models.IntegerField()
    max_y = models.IntegerField()
    svg = models.TextField()
    type=models.IntegerField(default=0)
    status = models.IntegerField(default=0)

class DataViewType(models.Model):
    class Meta:
        db_table = "data_view_type"
    title = models.TextField()
    code_type = models.TextField()
    comment = models.TextField(blank=True, null=True)

    def __unicode__(self):
        return self.title

class DataView(models.Model):
    class Meta:
        db_table = "data_view"
        ordering = ('position',)
        permissions = (
            ("can_administer", "Can administer data views"),
            ("can_browse", "Can browse data views")
        )
    title = models.TextField()
    data_view_type = models.ForeignKey(DataViewType)
    config = models.TextField(default="{}")
    is_default = models.BooleanField(default=False)
    position = models.IntegerField(default=0)
    comment = models.TextField(default="",blank=True,null=True)

    def save(self, *args, **kwargs):
        """ Does a post-save action: Make sure (only) one data view
        is the default.
        """
        super(DataView, self).save(*args, **kwargs)
        # We need to declare a default view if there is none. Also if
        # there is more than one default, reduce this to one. If the
        # current data view is marked default, this will be the one.
        # If there is exactly one default, nothing needs to be touched.
        default_views = DataView.objects.filter(is_default=True)
        if len(default_views) == 0:
            # Make the first data view the default one
            dv = DataView.objects.all()[0]
            dv.is_default = True
            dv.save()
        elif len(default_views) > 1 and self.is_default:
            # Have only the current data view as default
            for dv in default_views:
                if dv.id == self.id:
                    continue
                dv.is_default = False
                dv.save()
        elif len(default_views) > 1:
            # Mark all except the first one as not default
            for n,dv in enumerate(default_views):
                if n == 0:
                    continue
                dv.is_default = False
                dv.save()

class UserProfile(models.Model):
    """ A class that stores a set of custom user preferences.
    See: http://digitaldreamer.net/blog/2010/12/8/custom-user-profile-and-extend-user-admin-django/
    """
    user = models.OneToOneField(User)
    inverse_mouse_wheel = models.BooleanField(default=False)

    def __unicode__(self):
        return self.user.username

def create_user_profile(sender, instance, created, **kwargs):
    """ Create the UserProfile when a new User is saved.
    """
    if created:
        profile = UserProfile()
        profile.user = instance
        profile.save()

# Connect the a User object's post save signal to the profile
# creation
post_save.connect(create_user_profile, sender=User)

# ------------------------------------------------------------------------

# Include models for deprecated PHP-only tables, just so that we can
# remove them with South in a later migration.

class DeprecatedAppliedMigrations(models.Model):
    class Meta:
        db_table = "applied_migrations"
    id = models.CharField(max_length=32, primary_key=True)

class DeprecatedSession(models.Model):
    class Meta:
        db_table = "sessions"
    session_id = models.CharField(max_length=26)
    data = models.TextField(default='')
    last_accessed = models.DateTimeField(default=datetime.now)
