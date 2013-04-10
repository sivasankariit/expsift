# Create your views here.

from django.conf import settings
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.forms.widgets import SelectMultiple
from django.template import RequestContext
from django.core.urlresolvers import reverse
from django.forms import formsets
from django.forms.formsets import formset_factory
from django.utils import http
from django import forms
import base64
import datetime
import hashlib
import imp
import itertools
import os
import redis
import expsift.utils


class FilterForm(forms.Form):
    properties = forms.MultipleChoiceField(label='Filter Properties',
            widget=forms.SelectMultiple(attrs={'size':'10'}))
    choices = (('a','All'), ('g','Good only'),
               ('gu','Good or Unknown'),
               ('u','Unknown'), ('b','Bad'))
    goodbadfilter = forms.ChoiceField(widget = forms.RadioSelect,
                                      choices = choices)


    def __init__(self, properties = [], propValues = {}, *args, **kwargs):

        super(FilterForm, self).__init__(*args, **kwargs)

        propTuples = []
        for prop in sorted(properties):
            propTuples.append((prop, prop))

        self.fields['properties'].choices = propTuples

        for (property, pVals) in sorted(propValues.iteritems()):
            valTuples = []
            for val in sorted(pVals):
                valTuples.append((val, val))
            self.fields[property + '_values'] = forms.MultipleChoiceField(
                    label = property, choices = valTuples, required = False,
                    widget=forms.SelectMultiple(attrs={'size':'8'}))


# A custom BaseFormSet to create ExptForms with appropriate keyword arguments
# passed to the Form constructor
# The keyword argument 'unique_props' has to be a list of the set of unique
# properties for each ExptForm. The order of the sets in the list should be the
# same as the order of forms in the 'initial' keyword argument
class ExptBaseFormSet(formsets.BaseFormSet):

    def __init__(self, unique_props = [], *args, **kwargs):
        self.unique_props = unique_props
        super(ExptBaseFormSet, self).__init__(*args, **kwargs)


    def _construct_forms(self):
        # instantiate all the forms and put them in self.forms
        self.forms = []
        for i in xrange(self.total_form_count()):
            if self.unique_props:
                unique = self.unique_props[i]
            else:
                unique = []

            self.forms.append(self._construct_form(i, unique_props = unique))


class ExptForm(forms.Form):

    # Absolute directory path
    directory = forms.CharField(widget=forms.HiddenInput(),
                                required=False)

    # (Shortened) name displayed for the directory
    directory_display = forms.CharField(widget=forms.HiddenInput(),
                                        required=False)

    # URL of experiment directory
    directory_url = forms.CharField(widget=forms.HiddenInput(),
                                    required=False)

    # When was the experiment conducted? (Actually just the timestamp value
    # stored in the expsift_info file)
    timestamp = forms.DateTimeField(
            required = False,
            input_formats = ['%Y-%m-%d_%H:%M:%S.%f',
                             '%Y-%m-%d %H:%M:%S.%f',
                             '%Y-%m-%d_%H:%M:%S',
                             '%Y-%m-%d %H:%M:%S'])

    # Experiment is marked as good/bad/unknown
    expt_good = forms.NullBooleanField(
            required = False,
            widget=forms.Select(choices = ((None, 'Unknown'),
                                           (True, 'Good'),
                                           (False, 'Bad'))))

    # Properties from the expsift_tags file (text read from the file)
    properties_file = forms.CharField(required=False,
            widget=forms.Textarea(attrs={'rows':'8', 'cols':'30'}))
    properties_file_hidden = forms.CharField(widget=forms.HiddenInput(),
                                             required=False)

    # Comments from the expsift_comments file (text read from the file)
    comments_file = forms.CharField(required=False,
            widget=forms.Textarea(attrs={'rows':'8', 'cols':'40'}))
    comments_file_hidden = forms.CharField(widget=forms.HiddenInput(),
                                           required=False)

    # Is the experiment selected for comparison?
    compare_expt_select = forms.BooleanField(required=False)

    def __init__(self, unique_props = [], *args, **kwargs):
        super(ExptForm, self).__init__(*args, **kwargs)
        self.unique_properties = unique_props
        # Store the properties for the directory in a custom HTML5 data
        # attribute for the directory's checkbox.
        if unique_props:
            props_str = ' '.join([x.replace(' ', '___', 1) for x in unique_props])
            select_box = self.fields['compare_expt_select']
            select_box.widget.attrs.update({'data-expsift-uniq-props' : props_str})


class SelectDialogForm(forms.Form):

    def __init__(self, propValues = {}, *args, **kwargs):

        super(SelectDialogForm, self).__init__(*args, **kwargs)

        for (pName, pVals) in sorted(propValues.iteritems()):
            valTuples = []
            for val in sorted(pVals):
                valTuples.append((val, val))
            self.fields[pName+ '_values'] = forms.MultipleChoiceField(
                    label = pName, choices = valTuples, required = False,
                    widget=forms.SelectMultiple(attrs={'size':'8'}))


def redis_connect(host, port):
    properties_db = redis.StrictRedis(host, port, db=0)
    dir2properties_db = redis.StrictRedis(host, port, db=1)
    properties2dir_db = redis.StrictRedis(host, port, db=2)
    sha12dir_db = redis.StrictRedis(host, port, db=3)

    # Validate magic number keys of the databases
    assert(properties_db.get('magic_number') == '16378267')
    assert(dir2properties_db.get('magic_number') == '76378347')
    assert(properties2dir_db.get('magic_number') == '324728749')
    assert(sha12dir_db.get('magic_number') == '39916801')

    # Return a tuple with all 3 databases
    return (properties_db, dir2properties_db, properties2dir_db, sha12dir_db)


def getProperties(prop_db):
    propNames = prop_db.keys()
    propNames.remove('magic_number')

    propsDict = {}
    for pName in propNames:
        propsDict[pName] = prop_db.smembers(pName)

    return propsDict


def filterDirectories(prop2dir_db, crossVals):
    res_directories = set()
    for keys in crossVals:
        if not keys:
            continue
        directories = prop2dir_db.sinter(*keys)
        res_directories |= directories

    return res_directories


def getDirProperties(dir2prop_db, directories):
    res_props = {}
    for dir in directories:
        props = dir2prop_db.smembers(dir)
        res_props[dir] = props

    return res_props


def getDirTimestamps(dir2prop_db, directories):
    res_timestamps = {}
    for dir in directories:
        ts = dir2prop_db.get(dir + '__timestamp')
        if not ts:
            ts = '1970-01-01_00:00:00.000001'  # Default value
        res_timestamps[dir] = ts

    return res_timestamps


def getDirGood(dir2prop_db, directories):
    res_good = {}
    for dir in directories:
        expt_good = dir2prop_db.get(dir + '__goodbad')
        if expt_good == 'GOOD':
            res_good[dir] = True
        elif expt_good == 'BAD':
            res_good[dir] = False

    return res_good


def readDirTagsFiles(directories):
    max_file_size = getattr(settings, 'MAX_EXPSIFT_TAGS_FILE_SIZE', -1)
    res_files = {}
    for dir in directories:
        if (os.path.exists(os.path.join(dir, 'expsift_tags'))):
            tags_file = open(os.path.join(dir, 'expsift_tags'), 'r')
            str = tags_file.read(max_file_size)
            tags_file.close()
            res_files[dir] = str

    return res_files


def directoryActualUrl(directory):
    expt_logs_conf = getattr(settings, 'EXPT_LOGS', {})
    expt_logs_dir = expt_logs_conf['directory']
    return (reverse('expsift.views.home') +
            'expt-logs/' +  directory[len(expt_logs_dir):])


def directoryExptPageUrl(directory):
    return (reverse('expsift.views.individual_expt_base') + '?' +
            http.urlencode({'directory' : directory}, True))


def readDirCommentsFiles(directories):
    max_file_size = getattr(settings, 'MAX_EXPSIFT_COMMENTS_FILE_SIZE', -1)
    res_files = {}
    for dir in directories:
        if (os.path.exists(os.path.join(dir, 'expsift_comments'))):
            comments_file = open(os.path.join(dir, 'expsift_comments'), 'r')
            str = comments_file.read(max_file_size)
            comments_file.close()
            res_files[dir] = str

    return res_files


def createExptFormset(directories, dir2good_dict, dir2timestamps_dict,
                      dir2tagsfile_dict, dir2commentsfile_dict, unique_props):
    initial_form_data = []
    expt_logs_conf = getattr(settings, 'EXPT_LOGS', {})
    expt_logs_dir = expt_logs_conf['directory']
    expt_dir_max_len = expt_logs_conf['max_dir_length']
    ExptFormSet = formset_factory(ExptForm, formset = ExptBaseFormSet,
                                  extra=0, max_num=len(directories))
    unique_properties = []
    for dir in directories:
        # Ignore entry if the directory is not in the expt-logs root directory
        if not dir.startswith(expt_logs_dir):
            continue
        initial_dict = {}
        initial_dict['directory'] = dir
        dir_shortname = dir[ dir.rfind('/') + 1 : ][ : expt_dir_max_len]
        if len(dir) > len(dir_shortname):
            dir_shortname += '...'
        initial_dict['directory_display'] = dir_shortname
        if getattr(settings, 'ENABLE_INDIVIDUAL_EXPT_PAGE', False):
            initial_dict['directory_url'] = directoryExptPageUrl(dir)
        else:
            initial_dict['directory_url'] = directoryActualUrl(dir)
        if dir in dir2tagsfile_dict:
             initial_dict['properties_file'] = dir2tagsfile_dict[dir]
             initial_dict['properties_file_hidden'] = dir2tagsfile_dict[dir]
        if dir in dir2commentsfile_dict:
            initial_dict['comments_file'] = dir2commentsfile_dict[dir]
            initial_dict['comments_file_hidden'] = dir2commentsfile_dict[dir]
        initial_dict['timestamp'] = dir2timestamps_dict[dir]
        initial_dict['expt_good'] = dir2good_dict.get(dir, None)

        unique_properties.append(sorted(unique_props[dir]))
        initial_form_data.append(initial_dict)

    # Sort the experiments in reverse chronological order
    # Also sort the unique properties associated with the experiments.
    # For this we zip the two lists together, sort them and unzip
    form_data_and_props = zip(initial_form_data, unique_properties)
    form_data_and_props.sort(key=lambda item:item[0]['timestamp'], reverse=True)
    (initial_form_data_sorted,
     unique_properties_sorted) = zip(*form_data_and_props)

    formset = ExptFormSet(initial=initial_form_data_sorted,
                          unique_props = unique_properties_sorted)

    return formset


# Returns a new properties string where some old properties have been replaced,
# or added or updated.
def getUpdatedPropertiesString(old_properties_string,
                               update_old_prop_name, update_old_prop_value,
                               update_new_prop_name, update_new_prop_value):

    # Nothing to update in some corner cases:
    # 1. New property value is not specified
    if not update_new_prop_value:
        return old_properties_string
    # 2. New property name is not specified and old property name does not
    #    have to be retained
    elif (not update_new_prop_name and
          not update_old_prop_name):
        return old_properties_string

    # Check if the new property just needs to be added without checks
    if not update_old_prop_name and not update_old_prop_value:
        new_properties_string = ''
        # Copy the old properties
        for line in old_properties_string.splitlines():
            new_properties_string += line.rstrip() + '\n'
        # Add the new property
        new_properties_string += ''.join([update_new_prop_name, '=',
                                          update_new_prop_value, '\n'])

        return new_properties_string

    new_properties_string = ''
    for line in old_properties_string.splitlines():
        # Comment lines
        if line[0] == '#':
            new_properties_string += line.rstrip() + '\n'
            continue
        prop_val_str = line.rstrip()
        prop, val = expsift.utils.getPropNameAndValue(prop_val_str)
        # Old property has to be replaced if both name and value matches
        if (update_old_prop_name and
            update_old_prop_value and
            prop == update_old_prop_name and
            val == update_old_prop_value):
            new_properties_string += ''.join([update_new_prop_name, '=',
                                              update_new_prop_value, '\n'])

        # Old property has to be replaced if name matches
        elif (update_old_prop_name and
              prop == update_old_prop_name and
              update_new_prop_name):
            new_properties_string += ''.join([update_new_prop_name, '=',
                                              update_new_prop_value, '\n'])

        # Old property value has to be replaced if name matches and the property
        # name is retained
        elif (update_old_prop_name and
              prop == update_old_prop_name):
            new_properties_string += ''.join([update_old_prop_name, '=',
                                              update_new_prop_value, '\n'])

        # Old property is retained as is
        else:
            new_properties_string += prop_val_str + '\n'

    return new_properties_string


def updatePropertiesInDatabase(directory, properties_db,
                               dir2properties_db, properties2dir_db):

    assert(os.path.exists(os.path.join(directory, 'expsift_tags')))
    tags_file = open(os.path.join(directory, 'expsift_tags'), 'r')

    # Fetch the set of properties already in the database for this directory
    props_old = dir2properties_db.smembers(directory)

    # Remove all properties for this directory
    dir2properties_db.delete(directory)

    # Remove this directory from the set of directories for each of
    # those properties
    for prop in props_old:
        properties2dir_db.srem(prop, directory)

    # NOTE: We only update properties for this particular directory.
    # However it is possible that there are some set of values in the
    # properties_db directory for certain modified properties which are no
    # longer valid for any directory in the dataset.
    # Example:
    #    Initially prop1=val1 (only 1 directory has this value)
    #    So properties_db[prop1] = val1, ...
    #    After the edit, suppose prop1=val2
    #    Still properties_db[prop1] = val1, ...
    # If we are only adding new properties for existing experiments through the
    # web interface, this problem does not arise as existing values for
    # properties are not "revoked".
    # However it is advisable to update the entire redis index after flushing
    # out the databases when property values are changed.
    for line in tags_file:
        # Comment lines
        if line[0] == '#':
            continue
        prop_val_str = line.rstrip()
        line = prop_val_str.split('=', 1)
        assert(len(line) == 2)
        property = line[0]
        val = line[1]
        properties_db.sadd(property, val)
        dir2properties_db.sadd(directory, prop_val_str)
        properties2dir_db.sadd(prop_val_str, directory)
    tags_file.close()


def writePropertiesFile(directory, properties_str):
    if not os.path.exists(directory):
        return
    tags_file = open(os.path.join(directory, 'expsift_tags'), 'w')
    str = tags_file.write(properties_str)
    tags_file.close()


def writeCommentsFile(directory, comments_str):
    if not os.path.exists(directory):
        return
    comments_file = open(os.path.join(directory, 'expsift_comments'), 'w')
    str = comments_file.write(comments_str)
    comments_file.close()


def writeGoodBad(directory, val):
    if not os.path.exists(directory):
        return
    # Read current info file
    info_file_str = ''
    if os.path.exists(os.path.join(directory, 'expsift_info')):
        info_file = open(os.path.join(directory, 'expsift_info'), 'r')
        info_file_str = info_file.read()
        info_file.close()
    # Copy all lines other than the GOOD/BAD line
    str_new = ''
    for line in info_file_str.splitlines():
        if line == 'GOOD' or line == 'BAD':
            pass
        else:
            str_new += line + '\n'
    # Append the GOOD/BAD line
    if (val == True):
        str_new += 'GOOD\n'
    elif (val == False):
        str_new += 'BAD\n'
    info_file = open(os.path.join(directory, 'expsift_info'), 'w')
    info_file_str = info_file.write(str_new)
    info_file.close()


def goodbadfiltermatches(dir_val, filter_val):
    if filter_val == 'a':
        return True
    elif filter_val == 'g' and dir_val == True:
        return True
    elif filter_val == 'gu' and (dir_val == True or dir_val == None):
        return True
    elif filter_val == 'u' and dir_val == None:
        return True
    elif filter_val == 'b' and dir_val == False:
        return True
    else:
        return False


def home(request):
    redis_db_conf = getattr(settings, 'REDIS_DB', {})
    redis_db_name = redis_db_conf['host']
    redis_db_port = redis_db_conf['port']
    if not redis_db_name:
        return HttpResponse('Site settings do not specify Redis database name')

    (properties_db,
     dir2properties_db,
     properties2dir_db,
     sha12dir_db) = redis_connect(redis_db_name, redis_db_port)

    propNames = properties_db.keys()
    propNames.remove('magic_number')

    propsDict = getProperties(properties_db)

    form = FilterForm(properties = propsDict.keys(), propValues = propsDict,
                      initial={'goodbadfilter' : 'a'})

    return render_to_response('home/index.html',
                              {'propsDict' : propsDict,
                               'form' : form,
                               'show_prop_val_error' : '0'},
                               context_instance=RequestContext(request))


def filter(request):
    redis_db_conf = getattr(settings, 'REDIS_DB', {})
    redis_db_name = redis_db_conf['host']
    redis_db_port = redis_db_conf['port']
    if not redis_db_name:
        return HttpResponse('Site settings do not specify Redis database name')

    (properties_db,
     dir2properties_db,
     properties2dir_db,
     sha12dir_db) = redis_connect(redis_db_name, redis_db_port)

    propNames = properties_db.keys()
    propNames.remove('magic_number')

    propsDict = getProperties(properties_db)

    if request.method == 'GET':
        # Check if the request should be cleared
        if (request.GET['operation'] == 'Home'):
            form = FilterForm(properties = propsDict.keys(),
                              propValues = propsDict)
            return HttpResponseRedirect(reverse('expsift.views.home'))

        form = FilterForm(properties=propsDict.keys(),
                          propValues=propsDict,
                          data=request.GET)
        if form.is_valid():
            selected_properties = form.cleaned_data['properties']
            all_selected_vals = []
            has_some_selected_filters = False
            for prop in selected_properties:
                selected_val = form.cleaned_data[prop + '_values']
                # Only include those properties which have some selected values
                if len(selected_val):
                    db_keys = []
                    for val in selected_val:
                        db_keys.append(prop + "=" + val)
                    all_selected_vals.append(db_keys)
                    has_some_selected_filters = True
            if not has_some_selected_filters:
                return render_to_response('home/index.html',
                                          {'propsDict' : propsDict,
                                           'form' : form,
                                           'show_no_results_error' : '0',
                                           'show_prop_val_error' : '1'},
                                           context_instance=RequestContext(request))
            cross = itertools.product(*all_selected_vals)
            res_directories_db = filterDirectories(properties2dir_db, cross)

            # Check if directories need to be filtered by the validity
            # filters
            dir2good_dict = getDirGood(dir2properties_db, res_directories_db)
            goodbadfilter = form.cleaned_data['goodbadfilter']

            res_directories = [x for x in res_directories_db if goodbadfiltermatches(dir2good_dict.get(x, None), goodbadfilter)]

            templateQDict = {'propsDict' : propsDict, 'form' : form,
                             'show_prop_val_error' : '0'}

            if res_directories:
                dir2props_dict = getDirProperties(dir2properties_db,
                                                  res_directories)
                dir2tagsfile_dict = readDirTagsFiles(res_directories)
                dir2commentsfile_dict = readDirCommentsFiles(res_directories)
                dir2timestamps_dict = getDirTimestamps(dir2properties_db,
                                                       res_directories)

                (common_props, unique_props) = (
                        expsift.utils.getCommonAndUniqueProperties(dir2props_dict))

                unique_props_dict = {}
                for directory, props in unique_props.iteritems():
                    curr_props_dict = expsift.utils.getPropertyNameAndValues(props)
                    for prop_name, vals in curr_props_dict.iteritems():
                        if unique_props_dict.get(prop_name):
                            unique_props_dict[prop_name] |= vals
                        else:
                            unique_props_dict[prop_name] = vals

                select_form = SelectDialogForm(propValues = unique_props_dict)

                expt_formset = createExptFormset(res_directories,
                                                 dir2good_dict,
                                                 dir2timestamps_dict,
                                                 dir2tagsfile_dict,
                                                 dir2commentsfile_dict,
                                                 unique_props)
                templateQDict['show_no_results_error'] = '0'
                templateQDict['res_directories'] = res_directories
                templateQDict['dir2props_dict'] = dir2props_dict
                templateQDict['dir2tagsfile_dict'] = dir2tagsfile_dict
                templateQDict['dir2commentsfile_dict'] = dir2commentsfile_dict
                templateQDict['expt_formset'] = expt_formset
                templateQDict['select_dialog_form'] = select_form
                templateQDict['url_parameters'] = http.urlencode(request.GET, True)
                compare_functions = getattr(settings, 'COMPARE_FUNCTIONS', {})
                compare_operation_names = compare_functions.keys()
                templateQDict['compare_operations'] = compare_operation_names
            else:
                templateQDict['show_no_results_error'] = '1'

            return render_to_response('home/index.html', templateQDict,
                                      context_instance=RequestContext(request))

        else: # The form is invalid
            return render_to_response('home/index.html',
                                      {'propsDict' : propsDict,
                                       'form' : form,
                                       'show_no_results_error' : '0',
                                       'show_prop_val_error' : '0'},
                                       context_instance=RequestContext(request))
    else:
        return HttpResponse('Didn\'t expect a POST request. Shouldn\'t be here!')


def update_expts(request):
    redis_db_conf = getattr(settings, 'REDIS_DB', {})
    redis_db_name = redis_db_conf['host']
    redis_db_port = redis_db_conf['port']
    if not redis_db_name:
        return HttpResponse('Site settings do not specify Redis database name')

    (properties_db,
     dir2properties_db,
     properties2dir_db,
     sha12dir_db) = redis_connect(redis_db_name, redis_db_port)

    ExptFormSet = formset_factory(ExptForm, extra=0)
    if request.method == 'POST':
        formset = ExptFormSet(request.POST)
        if formset.is_valid():

            post_operation = request.POST['update_expts_operation']

            # Check if a new tag (property) must be added to selected
            # directories
            if (post_operation == 'Update Tag'):
                update_old_prop_name = request.POST['update_old_prop_name']
                update_old_prop_value = request.POST['update_old_prop_value']
                update_new_prop_name = request.POST['update_new_prop_name']
                update_new_prop_value = request.POST['update_new_prop_value']

                # Get the old properties for each of the selected directories
                selected_expt_old_props = {}
                for form in formset:
                    if form.cleaned_data['compare_expt_select']:
                        directory = form.cleaned_data['directory']
                        props_file_old = (
                                form.cleaned_data['properties_file_hidden'])
                        selected_expt_old_props[directory] = props_file_old

                # Update properties in the selected directories
                if selected_expt_old_props:
                    for directory, props_file_old in selected_expt_old_props.iteritems():
                        props_file_new = getUpdatedPropertiesString(
                                props_file_old, update_old_prop_name,
                                update_old_prop_value, update_new_prop_name,
                                update_new_prop_value)
                        if (os.path.exists(directory)):
                            writePropertiesFile(directory, props_file_new)
                            updatePropertiesInDatabase(directory, properties_db,
                                                       dir2properties_db,
                                                       properties2dir_db)
                # Redirect back to the page from where the POST was made
                return HttpResponseRedirect(reverse('expsift.views.filter')+'?'+http.urlencode(request.GET, True))

            # Check if the requested operation is to just output the selected
            # directory names
            elif (post_operation == 'Show Expt Dirs'):
                # Check which directories have been selected
                selected_expts_sha1 = []
                for form in formset:
                    if form.cleaned_data['compare_expt_select']:
                        directory = form.cleaned_data['directory']
                        sha1 = hashlib.sha1(directory)
                        b64_sha1 = base64.b64encode(sha1.digest())
                        selected_expts_sha1.append(b64_sha1)
                # Pass the SHA1 hash of the experiment directories as part of
                # the query string so that we can support more directories in
                # a GET request.
                if selected_expts_sha1:
                    return HttpResponseRedirect(reverse('expsift.views.show_expt_directories')+'?'+http.urlencode({'sel_expts_sha1' : selected_expts_sha1}, True))
                else:
                    return HttpResponseRedirect(reverse('expsift.views.show_expt_directories'))

            # Check if a compare function should be called.
            # NOTE: This should really be just a GET operation, but there is no
            # easy way to intersperse the 'compare_expt select' form checkboxes
            # and the actual experiment forms which are used for the POST
            # operation.
            # We will just redirect to a new address though. That address can be
            # used to get the same comparison page directly if required.
            elif (post_operation != 'Update Experiments'):
                # Check which directories must be included in the comparison
                selected_expts_sha1 = []
                for form in formset:
                    if form.cleaned_data['compare_expt_select']:
                        directory = form.cleaned_data['directory']
                        sha1 = hashlib.sha1(directory)
                        b64_sha1 = base64.b64encode(sha1.digest())
                        selected_expts_sha1.append(b64_sha1)
                if selected_expts_sha1:
                    return HttpResponseRedirect(reverse('expsift.views.compare_expts_base')+'?'+http.urlencode({'sel_expts_sha1' : selected_expts_sha1, 'compare_operation' : post_operation}, True))
                else:
                    return HttpResponseRedirect(reverse('expsift.views.compare_expts_base')+'?'+http.urlencode({'compare_operation' : post_operation}, True))

            # Update Experiments operation. Write the new comments or properties
            # files as appropriate
            for form in formset:
                # Check if properties have to be updated for this directory
                dir = form.cleaned_data['directory']
                if (form.cleaned_data['properties_file'] !=
                    form.cleaned_data['properties_file_hidden']):
                    if (os.path.exists(dir)):
                        writePropertiesFile(dir, form.cleaned_data['properties_file'])
                        updatePropertiesInDatabase(dir, properties_db,
                                                   dir2properties_db,
                                                   properties2dir_db)

                # Check if comments file has to be written
                if (form.cleaned_data['comments_file'] !=
                    form.cleaned_data['comments_file_hidden']):
                    if (os.path.exists(dir)):
                        writeCommentsFile(dir, form.cleaned_data['comments_file'])

                # Check if expt_good / bad info has to be written
                if ((form.cleaned_data['expt_good'] == True) and
                    (dir2properties_db.get(dir + '__goodbad') != 'GOOD')):
                   writeGoodBad(dir, True)
                   dir2properties_db.set(dir+ '__goodbad', 'GOOD')
                elif ((form.cleaned_data['expt_good'] == False) and
                      (dir2properties_db.get(dir + '__goodbad') != 'BAD')):
                   writeGoodBad(dir, False)
                   dir2properties_db.set(dir+ '__goodbad', 'BAD')
                elif ((form.cleaned_data['expt_good'] == None) and
                      (dir2properties_db.get(dir + '__goodbad') != None)):
                   writeGoodBad(dir, None)
                   dir2properties_db.delete(dir+ '__goodbad')


            # Redirect back to the page from where the POST was made
            return HttpResponseRedirect(reverse('expsift.views.filter')+'?'+http.urlencode(request.GET, True))

        else:
            return HttpResponse('Some invalid data in forms')
    else:
        return HttpResponse('Request method is not POST. Shouldn\'t be here!')


def compare_expts_base(request):
    redis_db_conf = getattr(settings, 'REDIS_DB', {})
    redis_db_name = redis_db_conf['host']
    redis_db_port = redis_db_conf['port']
    if not redis_db_name:
        return HttpResponse('Site settings do not specify Redis database name')

    (properties_db,
     dir2properties_db,
     properties2dir_db,
     sha12dir_db) = redis_connect(redis_db_name, redis_db_port)

    if not 'compare_operation' in request.GET:
        return HttpResponse('No compare operation specified')

    compare_operation = request.GET['compare_operation']
    compare_functions = getattr(settings, 'COMPARE_FUNCTIONS', {})
    compare_func_spec = compare_functions.get(compare_operation, {})

    # Check if a valid compare operation was specified
    if not compare_func_spec:
        return HttpResponse('Requested compare operation "' +
                            compare_operation + '" not available.')

    if 'sel_expts_sha1' in request.GET:
        sel_directories_sha1 = list(request.GET.getlist('sel_expts_sha1'))
        sel_directories = [ sha12dir_db.get(digest) for digest in sel_directories_sha1 ]
        dir2props_dict = getDirProperties(dir2properties_db, sel_directories)
    else:
        dir2props_dict = {}

    if settings.DEBUG:
        fp, pathname, desc = imp.find_module(compare_func_spec['module_name'])
        mod = imp.load_module(compare_func_spec['module_name'], fp, pathname, desc)
        compare_func = getattr(mod, compare_func_spec['method_name'])
        return compare_func(dir2props_dict)
    else:
        try:
            fp, pathname, desc = imp.find_module(compare_func_spec['module_name'])
            try:
                mod = imp.load_module(compare_func_spec['module_name'], fp, pathname, desc)
                compare_func = getattr(mod, compare_func_spec['method_name'])
                return compare_func(dir2props_dict)
            except Exception, err:
                print 'ERROR: %s' % str(err)
            finally:
                if fp:
                    fp.close()
        except:
            print ('Exception while trying to find comparison module:',
                   compare_func_spec['module_name'])


    return HttpResponse('Requested expts = ' + str(sel_directories))


def show_expt_directories(request):
    redis_db_conf = getattr(settings, 'REDIS_DB', {})
    redis_db_name = redis_db_conf['host']
    redis_db_port = redis_db_conf['port']
    if not redis_db_name:
        return HttpResponse('Site settings do not specify Redis database name')

    (properties_db,
     dir2properties_db,
     properties2dir_db,
     sha12dir_db) = redis_connect(redis_db_name, redis_db_port)

    if 'sel_expts_sha1' in request.GET:
        sel_directories_sha1 = list(request.GET.getlist('sel_expts_sha1'))
        sel_directories = [ sha12dir_db.get(digest) for digest in sel_directories_sha1 ]
        dir2props_dict = getDirProperties(dir2properties_db, sel_directories)
        (common_props, unique_props) = (
                expsift.utils.getCommonAndUniqueProperties(dir2props_dict))
        unique_props_str = []  # list of tuples (dir, props)
        for directory, props in unique_props.iteritems():
            unique_props_str.append((directory, ', '.join(sorted(props))))
        # Sort directories by their unique property strings
        unique_props_str.sort(key=lambda item:item[1])
        return render_to_response('home/expt_directories.html',
                                  { 'unique_props' : unique_props_str },
                                  context_instance=RequestContext(request))

    else:
        return HttpResponse('No experiment directories selected.')


def individual_expt_base(request):
    redis_db_conf = getattr(settings, 'REDIS_DB', {})
    redis_db_name = redis_db_conf['host']
    redis_db_port = redis_db_conf['port']
    if not redis_db_name:
        return HttpResponse('Site settings do not specify Redis database name')

    (properties_db,
     dir2properties_db,
     properties2dir_db,
     sha12dir_db) = redis_connect(redis_db_name, redis_db_port)

    expt_logs_conf = getattr(settings, 'EXPT_LOGS', {})
    expt_logs_dir = expt_logs_conf['directory']

    if request.GET['directory']:
        expt_dir = request.GET['directory']
        # Check if expt_dir is in the expt-logs root directory
        if not expt_dir.startswith(expt_logs_dir):
            return HttpResponse('Experiment directory incorrectly specified.')

        dir2props_dict = getDirProperties(dir2properties_db, [expt_dir])

        props_sorted = sorted(dir2props_dict[expt_dir])
        max_prop_len = 0
        for prop in props_sorted:
            if max_prop_len < len(prop):
                max_prop_len = len(prop)
        if max_prop_len <= 30:
            props_cols = 4
        elif max_prop_len <= 45:
            props_cols = 3
        elif max_prop_len <= 60:
            props_cols = 2
        else:
            props_cols = 1

        # Store template variables for the default individual experiment page
        templateQDict = {'directory': expt_dir}
        templateQDict['directory_url'] = directoryActualUrl(expt_dir)
        templateQDict['properties'] = props_sorted
        templateQDict['properties_cols'] = props_cols

        # Check if a custom function has been configured to generate the
        # experiment page
        expt_page_func_spec = getattr(settings, 'INDIVIDUAL_EXPT_PAGE_FUNC', {})
        expt_page_module_name = expt_page_func_spec.get('module_name', '')
        expt_page_method_name = expt_page_func_spec.get('method_name', '')
        if not expt_page_module_name or not expt_page_method_name:
            # Return the default experiment page
            return render_to_response('expt/individual.html', templateQDict,
                                      context_instance=RequestContext(request))

        # Find the configured response generator method and execute it
        if settings.DEBUG:
            fp, pathname, desc = imp.find_module(expt_page_module_name)
            mod = imp.load_module(expt_page_module_name, fp, pathname, desc)
            expt_page_func = getattr(mod, expt_page_method_name)
            return expt_page_func(expt_dir, dir2props_dict[expt_dir], templateQDict)
        else:
            try:
                fp, pathname, desc = imp.find_module(expt_page_module_name)
                try:
                    mod = imp.load_module(expt_page_module_name, fp, pathname, desc)
                    expt_page_func = getattr(mod, expt_page_method_name)
                    return expt_page_func(expt_dir, dir2props_dict[expt_dir], templateQDict)
                except Exception, err:
                    print 'ERROR: %s' % str(err)
                finally:
                    if fp:
                        fp.close()
            except:
                print ('Exception while trying to load individual experiment page module:',
                       expt_page_module_name)
        return HttpResponse('Requested expt directory = ' + expt_dir)
    else:
        return HttpResponse('Experiment directory not specified in request.')
