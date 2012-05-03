# Create your views here.

from django.conf import settings
from django.http import HttpResponse #TODO: remove
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.forms.widgets import SelectMultiple
from django.template import RequestContext
from django.core.urlresolvers import reverse
from django.forms.formsets import formset_factory
from django.utils import http
from django import forms
import datetime
import imp
import itertools
import os
import redis


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


class ExptForm(forms.Form):
    directory = forms.CharField(widget=forms.HiddenInput(),
                                required=False)
    directory_display = forms.CharField(widget=forms.HiddenInput(),
                                        required=False)
    directory_url = forms.CharField(widget=forms.HiddenInput(),
                                    required=False)
    timestamp = forms.DateTimeField(
            required = False,
            input_formats = ['%Y-%m-%d_%H:%M:%S.%f',
                             '%Y-%m-%d %H:%M:%S.%f',
                             '%Y-%m-%d_%H:%M:%S',
                             '%Y-%m-%d %H:%M:%S'])
    expt_good = forms.NullBooleanField(
            required = False,
            widget=forms.Select(choices = ((None, 'Unknown'),
                                           (True, 'Good'),
                                           (False, 'Bad'))))
    expsift_info_error = forms.BooleanField(required=False)
    properties_file = forms.CharField(required=False,
            widget=forms.Textarea(attrs={'rows':'8', 'cols':'20'}))
    properties_file_hidden = forms.CharField(widget=forms.HiddenInput(),
                                             required=False)
    comments_file = forms.CharField(required=False,
            widget=forms.Textarea(attrs={'rows':'8', 'cols':'40'}))
    comments_file_hidden = forms.CharField(widget=forms.HiddenInput(),
                                           required=False)
    multiplot_select = forms.BooleanField(required=False)


def redis_connect(host, port):
    properties_db = redis.StrictRedis(host, port, db=0)
    dir2properties_db = redis.StrictRedis(host, port, db=1)
    properties2dir_db = redis.StrictRedis(host, port, db=2)

    # Validate magic number keys of the databases
    assert(properties_db.get('magic_number') == '16378267')
    assert(dir2properties_db.get('magic_number') == '76378347')
    assert(properties2dir_db.get('magic_number') == '324728749')

    # Return a tuple with all 3 databases
    return (properties_db, dir2properties_db, properties2dir_db)


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
                      dir2tagsfile_dict, dir2commentsfile_dict):
    initialFormData = []
    expt_logs_conf = getattr(settings, 'EXPT_LOGS', {})
    expt_logs_dir = expt_logs_conf['directory']
    expt_dir_max_len = expt_logs_conf['max_dir_length']
    ExptFormSet = formset_factory(ExptForm, extra=0, max_num=len(directories))
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
        initial_dict['directory_url'] = (reverse('expsift.views.home') +
                'expt-logs/' +  dir[len(expt_logs_dir):])
        if dir in dir2tagsfile_dict:
             initial_dict['properties_file'] = dir2tagsfile_dict[dir]
             initial_dict['properties_file_hidden'] = dir2tagsfile_dict[dir]
        if dir in dir2commentsfile_dict:
            initial_dict['comments_file'] = dir2commentsfile_dict[dir]
            initial_dict['comments_file_hidden'] = dir2commentsfile_dict[dir]
        initial_dict['timestamp'] = dir2timestamps_dict[dir]
        initial_dict['expt_good'] = dir2good_dict.get(dir, None)

        initialFormData.append(initial_dict)
    # Sort the experiments in reverse chronological order
    initialFormData.sort(key=lambda item:item['timestamp'], reverse=True)

    formset = ExptFormSet(initial=initialFormData)

    return formset


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
        prop_val_str = line.strip()
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
     properties2dir_db) = redis_connect(redis_db_name, redis_db_port)

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
     properties2dir_db) = redis_connect(redis_db_name, redis_db_port)

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
                dir2props_dict = getDirProperties(dir2properties_db, res_directories)
                dir2tagsfile_dict = readDirTagsFiles(res_directories)
                dir2commentsfile_dict = readDirCommentsFiles(res_directories)
                dir2timestamps_dict = getDirTimestamps(dir2properties_db, res_directories)
                expt_formset = createExptFormset(res_directories,
                                                 dir2good_dict,
                                                 dir2timestamps_dict,
                                                 dir2tagsfile_dict,
                                                 dir2commentsfile_dict)
                templateQDict['show_no_results_error'] = '0'
                templateQDict['res_directories'] = res_directories
                templateQDict['dir2props_dict'] = dir2props_dict
                templateQDict['dir2tagsfile_dict'] = dir2tagsfile_dict
                templateQDict['dir2commentsfile_dict'] = dir2commentsfile_dict
                templateQDict['expt_formset'] = expt_formset
                templateQDict['url_parameters'] = http.urlencode(request.GET, True)
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
     properties2dir_db) = redis_connect(redis_db_name, redis_db_port)

    ExptFormSet = formset_factory(ExptForm, extra=0)
    if request.method == 'POST':
        formset = ExptFormSet(request.POST)
        if formset.is_valid():

            # Check if a multiplot should be generated.
            # NOTE: This should really be just a GET operation, but there is no
            # easy way to intersperse the 'multiplot select' form checkboxes and
            # the actual experiment forms which are used for the POST operation.
            # We will just redirect to a new address though. That address can be
            # used to get the same multiplot directly if required.
            if (request.POST['update_expts_operation'] == 'Multiplot'):
                # TODO: Add stuff here
                # Check which directories must be included in the multiplot
                selected_expts = []
                for form in formset:
                    dir = form.cleaned_data['directory']
                    if form.cleaned_data['multiplot_select']:
                        selected_expts.append(dir)
                if selected_expts:
                    return HttpResponseRedirect(reverse('expsift.views.multiplot_base')+'?'+http.urlencode({'selected_expts' : selected_expts}, True))
                else:
                    return HttpResponseRedirect(reverse('expsift.views.multiplot_base'))


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


def multiplot_base(request):
    redis_db_conf = getattr(settings, 'REDIS_DB', {})
    redis_db_name = redis_db_conf['host']
    redis_db_port = redis_db_conf['port']
    if not redis_db_name:
        return HttpResponse('Site settings do not specify Redis database name')

    (properties_db,
     dir2properties_db,
     properties2dir_db) = redis_connect(redis_db_name, redis_db_port)

    m_settings = getattr(settings, 'MULTIPLOT', {})
    sel_directories = list(request.GET.getlist('selected_expts'))

    dir2props_dict = getDirProperties(dir2properties_db, sel_directories)

    try:
        fp, pathname, desc = imp.find_module(m_settings['module_name'])
        try:
            mod = imp.load_module(m_settings['module_name'], fp, pathname, desc)
            multiplot_func = getattr(mod, m_settings['method_name'])
            return multiplot_func(dir2props_dict)
        except Exception, err:
            print 'ERROR: %s' % str(err)
        finally:
            if fp:
                fp.close()
    except:
        print 'Exception while trying to find module'


    return HttpResponse('Requested expts = ' + str(request.GET.getlist('selected_expts')))
