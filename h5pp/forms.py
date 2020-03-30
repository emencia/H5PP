import json
import os
from pathlib import Path

from django import forms
from django.conf import settings
from h5pp.models import h5p_libraries
from h5pp.h5p.h5pclasses import H5PDjango
from h5pp.h5p.h5pmodule import h5p_insert
from h5pp.h5p.editor.h5peditormodule import createContent


def handleUploadedFile(files, filename):
    """
    Function to handle uploading h5p file
    """
    # TODO Figure out if filename is protected against injection attacks

    tmpdir = Path(settings.H5P_STORAGE_ROOT) / 'tmp'

    if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)
    file_path = tmpdir / filename

    with open(file_path, 'wb+') as destination:
        for chunk in files.chunks():
            destination.write(chunk)

    return {'folderPath': tmpdir, 'path': file_path}


class LibrariesForm(forms.Form):
    """
    Form for uploading and updating h5p libraries

    """

    h5p = forms.FileField(required=False)
    download = forms.BooleanField(widget=forms.CheckboxInput(), required=False)
    uninstall = forms.BooleanField(widget=forms.CheckboxInput(), required=False)

    def __init__(self, user, *args, **kwargs):
        super(LibrariesForm, self).__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        h5pfile = self.cleaned_data.get('h5p')
        down = self.cleaned_data.get('download')
        unins = self.cleaned_data.get('uninstall')

        if h5pfile is not None:
            if down is not False or unins is not False:
                raise forms.ValidationError('Too many choices selected.')
            interface = H5PDjango(self.user)
            paths = handleUploadedFile(h5pfile, h5pfile.name)
            validator = interface.h5pGetInstance('validator', paths['folderPath'], paths['path'])

            if not validator.is_valid_package(True, False):
                raise forms.ValidationError('The uploaded file was not a valid h5p package.')

            storage = interface.h5pGetInstance('storage')
            if not storage.save_package(None, None, True):
                raise forms.ValidationError('Error during library save.')
        elif down:
            if unins:
                raise forms.ValidationError('Too many choices selected.')
            libraries = list(h5p_libraries.objects.values())
            if not len(libraries) > 0:
                raise forms.ValidationError('You cannot update libraries when you don\'t have libraries installed !.')

            interface = H5PDjango(self.user)
            interface.updateTutorial()
        elif unins:
            raise forms.ValidationError('No actions selected.')

        return self.cleaned_data


CHOICES = [('upload', 'Upload'), ('create', 'Create')]


class CreateForm(forms.Form):
    """
    Form for upload h5p file

    """

    title = forms.CharField(label='Title ')
    h5p_type = forms.ChoiceField(choices=CHOICES, widget=forms.RadioSelect())
    h5p = forms.FileField(label='HTML 5 Package ',
                          help_text='Select a .h5p file to upload and create interactive content from. You may start with the <a href="http://h5p.org/content-types-and-applications" target="_blank">example files</a> on H5P.org',
                          required=False)
    json_content = forms.CharField(widget=forms.HiddenInput())
    disable = forms.IntegerField(widget=forms.HiddenInput())
    h5p_library = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, request, *args, **kwargs):
        super(CreateForm, self).__init__(*args, **kwargs)
        self.request = request
        self.fields['title'].initial = self.getTitle()
        self.fields['json_content'].initial = self.getJsonContent()
        self.fields['disable'].initial = self.getDisable()
        self.fields['h5p_library'].initial = self.getLibrary()

    def clean(self):
        if self.request.POST['h5p_type'] == 'upload':
            h5pfile = self.cleaned_data.get('h5p')
            if not h5pfile:
                raise forms.ValidationError('You need to choose a valid h5p package.')

            interface = H5PDjango(self.request.user)
            paths = handleUploadedFile(h5pfile, h5pfile.name)
            validator = interface.h5pGetInstance('validator', paths['folderPath'], paths['path'])

            if not validator.is_valid_package(False, False):
                raise forms.ValidationError('The uploaded file was not a valid h5p package.')

            self.request.POST['h5p_upload'] = paths['path']
            self.request.POST['h5p_upload_folder'] = paths['folderPath']
            if not h5p_insert(self.request, interface):
                raise forms.ValidationError('Error during saving the content.')
        else:
            interface = H5PDjango(self.request.user)
            core = interface.h5pGetInstance('core')
            content = dict()
            content['disable'] = 0
            libraryData = core.library_from_string(self.request.POST['h5p_library'])
            if not libraryData:
                raise forms.ValidationError('You must choose an H5P content type or upload an H5P file.')
            else:
                content['library'] = libraryData
                runnable = h5p_libraries.objects.filter(machine_name=libraryData['machineName'],
                                                        major_version=libraryData['majorVersion'],
                                                        minor_version=libraryData['minorVersion']).values('runnable')
                if not len(runnable) > 0 and runnable[0]['runnable'] == 0:
                    raise forms.ValidationError('Invalid H5P content type')

                content['library']['libraryId'] = core.h5p_framework.get_library_id(content['library']['machineName'],
                                                                           content['library']['majorVersion'],
                                                                           content['library']['minorVersion'])
                if not content['library']['libraryId']:
                    raise forms.ValidationError('No such library')

                content['title'] = self.request.POST['title']
                content['params'] = self.request.POST['json_content']
                content['author'] = self.request.user.username
                params = json.loads(content['params'])
                if 'contentId' in self.request.POST:
                    content['id'] = self.request.POST['contentId']
                content['id'] = core.save_content(content)

                if not createContent(self.request, content, params):
                    raise forms.ValidationError('Impossible to create the content')

                return content['id']

        return self.cleaned_data

    def getJsonContent(self):
        if 'json_content' in self.request.GET or 'translation_source' in self.request.GET and 'json_content' in \
            self.request.GET['translation_source']:
            filteredParams = self.request.GET['json_content'] if 'translation_source' not in self.request.GET else \
            self.request.GET['translation_source']['json_content']
        else:
            filteredParams = '{}'

        return filteredParams

    def getLibrary(self):
        if 'h5p_library' in self.request.GET:
            return self.request.GET['h5p_library']
        else:
            return 0

    def getDisable(self):
        if 'disable' in self.request.GET:
            return self.request.GET['disable']
        else:
            return 0

    def getTitle(self):
        if 'title' in self.request.GET:
            return self.request.GET['title']
        else:
            return ''
