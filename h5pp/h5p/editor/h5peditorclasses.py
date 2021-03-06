# Handles all communication with the database

import collections
import shutil
import json
import re
import os
import urllib.parse
from pathlib import Path

from django.conf import settings


class H5PDjangoEditor:
    global buildBase
    buildBase = None

    ##
    # Constructor for the core editor library
    ##
    def __init__(self, h5p, storage, basePath, filesDir, editorFilesDir=None):
        self.h5p = h5p
        self.storage = storage
        self.basePath = basePath
        self.contentFilesDir = Path(filesDir) / 'content'
        if editorFilesDir is None:
            self.editorFilesDir = Path(filesDir) / 'editor'
        else:
            self.editorFilesDir = Path(editorFilesDir) / 'editor'

    ##
    # This does alot of the same as getLibraries in library/h5pclasses.py. Use that instead ?
    ##
    def getLibraries(self, request):
        if 'libraries[]' in request.POST:
            lib = dict(request.POST.lists())
            liblist = list()
            for name in lib['libraries[]']:
                liblist.append(name)
            libraries = list()
            for libraryName in liblist:
                matches = re.search('(.+)\s(\d+)\.(\d+)$', libraryName)
                if matches:
                    libraries.append(
                        {'uberName': libraryName, 'name': matches.group(1), 'majorVersion': matches.group(2),
                         'minorVersion': matches.group(3)})

        libraries = self.storage.getLibraries(libraries if 'libraries' in locals() else None)

        # TODO Remove nonfunctional devmode
        # if self.h5p.development_mode:
        #     devLibs = self.h5p.h5pD.getLibraries()
        #
        #     for i in range(0, len(libraries)):
        #         if devLibs:
        #             lid = libraries[i]['name'] + ' ' + libraries[i]['majorVersion'] + '.' +\
        #                   libraries[i]['minorVersion']
        #             if 'lid' in devLibs:
        #                 libraries[i] = {'uberName': lid, 'name': devLibs[lid]['machineName'],
        #                                 'title': devLibs[lid]['title'], 'majorVersion': devLibs[lid]['majorVersion'],
        #                                 'minorVersion': devLibs[lid]['minorVersion'],
        #                                 'runnable': devLibs[lid]['runnable'],
        #                                 'restricted': libraries[i]['restricted'],
        #                                 'tutorialUrl': libraries[i]['tutorialUrl'], 'isOld': libraries[i]['isOld']}

        return json.dumps(libraries)

    ##
    # Get all scripts, css and semantics data for a library
    ##
    def getLibraryData(self, machineName, majorVersion, minorVersion, langageCode, prefix=''):
        libraries = self.findEditorLibraries(machineName, majorVersion, minorVersion)
        libraryData = dict()
        libraryData['semantics'] = self.h5p.load_library_semantics(machineName, majorVersion, minorVersion)
        libraryData['language'] = self.getLibraryLanguage(machineName, majorVersion, minorVersion, langageCode)

        # TODO Fix or remove nonfunctional aggregateAssets tech
        # aggregateAssets = self.h5p.aggregateAssets
        # self.h5p.aggregateAssets = False

        files = self.h5p.get_dependencies_files(libraries)

        # TODO Fix or remove nonfunctional aggregateAssets tech
        # self.h5p.aggregateAssets = aggregateAssets

        # Create base URL
        url = urllib.parse.urljoin(settings.MEDIA_URL, 'h5pp/')
        url = urllib.parse.urljoin(url, prefix)
        # url = settings.MEDIA_URL + '/h5pp' + prefix

        # JavaScripts
        if 'scripts' in files:
            for script in files['scripts']:
                if re.search('/:\/\//', script['path']):
                    # External file
                    if 'javascript' not in libraryData:
                        libraryData['javascript'] = collections.OrderedDict()
                    libraryData['javascript'][script['path'] + script['version']] = '\n' + script['path'].read()
                else:
                    # Local file
                    if 'javascript' not in libraryData:
                        libraryData['javascript'] = collections.OrderedDict()

                    libraryData['javascript'][url + script['path'] + script['version']] = '\n' + self.h5p.fs.get_content(
                        script['path'])

        # Stylesheets
        if 'styles' in files:
            for css in files['styles']:
                if re.search('/:\/\//', css['path']):
                    # External file
                    if 'css' not in libraryData:
                        libraryData['css'] = dict()
                    libraryData['css'][css['path'] + css['version']] = css['path'].read()
                else:
                    # Local file
                    if 'css' not in libraryData:
                        libraryData['css'] = dict()
                    self.buildCssPath(None, url + os.path.dirname(css['path']) + '/')
                    libraryData['css'][url + css['path'] + css['version']] = re.sub(
                        '(?i)url\([\']?(?![a-z]+:|\/+)([^\')]+)[\']?\)', self.buildCssPath,
                        self.h5p.fs.get_content(css['path']))

        # Add translations for libraries
        for key, library in list(libraries.items()):
            language = self.getLibraryLanguage(library['machine_name'], library['major_version'],
                                               library['minor_version'], langageCode)
            if language is not None:
                lang = '; H5PEditor.language["' + library['machine_name'] + '"] = ' + language + ';'
                libraryData['javascript'][lang] = lang

        return json.dumps(libraryData)

    ##
    # Return all libraries used by the given editor library
    ##
    def findEditorLibraries(self, machineName, majorVersion, minorVersion):
        library = self.h5p.load_library(machineName, majorVersion, minorVersion)
        dependencies = dict()
        self.h5p.find_library_dependencies(dependencies, library)

        # Order dependencies by weight
        orderedDependencies = collections.OrderedDict()
        for i in range(1, len(dependencies) + 1):
            for key, dependency in list(dependencies.items()):
                if dependency['weight'] == i and dependency['type'] == 'editor':
                    # Only load editor libraries
                    dependency['library']['id'] = dependency['library']['library_id']
                    orderedDependencies[dependency['library']['library_id']] = dependency['library']
                    break

        return orderedDependencies

    def getLibraryLanguage(self, machineName, majorVersion, minorVersion, langageCode):
        language = self.storage.getLanguage(machineName, majorVersion, minorVersion, langageCode)
        return None if language == False else language

    ##
    # Create directories for uploaded content
    ##
    def createDirectories(self, contentId):
        self.contentDirectory = self.contentFilesDir / str(contentId)
        if not os.path.isdir(self.contentFilesDir):
            os.mkdir(self.basePath / self.contentFilesDir)

        subDirectories = ['', 'files', 'images', 'videos', 'audios']
        for subDirectory in subDirectories:
            subDirectory = self.contentDirectory / subDirectory
            if not os.path.isdir(subDirectory):
                os.mkdir(subDirectory)

        return True

    ##
    # Move uploaded files, remove old files and update library usage
    ##
    def processParameters(self, contentId, newLibrary, newParameters, oldLibrary=None, oldParameters=None):
        newFiles = list()
        oldFiles = list()
        field = {'type': 'library'}
        libraryParams = {'library': self.h5p.library_to_string(newLibrary), 'params': newParameters}
        self.processField(field, libraryParams, newFiles)
        if oldLibrary is not None:
            old_semantics = self.h5p.load_library_semantics(
                oldLibrary['name'], oldLibrary['majorVersion'],
                oldLibrary['minorVersion'], oldParameters
            )

            #TODO Parameter params unfilled...
            self.processSemantics(oldFiles, old_semantics)

            for i in range(0, len(oldFiles)):
                if not oldFiles[i] in newFiles and not re.search('(?i)^(\w+:\/\/|\.\.\/)', oldFiles[i]):
                    removeFile = self.contentDirectory + oldFiles[i]
                    del removeFile
                    self.storage.removeFile(removeFile)

    ##
    # Recursive function that moves the new files in to the h5p content folder and generates a list over the old files
    # Also locates all the libraries
    ##
    def processSemantics(self, files, semantics, params):
        for i in range(0, len(semantics)):
            field = semantics[i]
            if not field['name'] in params:
                continue
            self.processField(field, params[field['name']], files)

    ##
    # Process a single field
    ##
    def processField(self, field, params, files):
        if field['type'] == 'image' or field['type'] == 'file':
            if 'path' in params:
                self.processFile(params, files)
                if 'originalImage' in params and 'path' in params['originalImage']:
                    self.processFile(params['originalImage'], files)
            return
        elif field['type'] == 'audio' or field['type'] == 'video':
            if isinstance(params, list):
                for i in range(0, len(params)):
                    self.processFile(params[i], files)
            return
        elif field['type'] == 'library':
            if 'library' in params and 'params' in params:
                library = self.libraryFromString(params['library'])
                semantics = self.h5p.load_library_semantics(library['machineName'], library['majorVersion'],
                                                            library['minorVersion'])
                self.processSemantics(files, semantics, params['params'])
            return
        elif field['type'] == 'group':
            if params:
                if len(field['fields']) == 1:
                    params = {field['fields'][0]['name']: params}
                self.processSemantics(files, field['fields'], params)
            return
        elif field['type'] == 'list':
            if isinstance(params, list):
                for j in range(0, len(params)):
                    self.processField(field['field'], params[j], files)
            return
        return

    def processFile(self, params, files):
        editorPath = self.editorFilesDir

        matches = re.search(self.h5p.relativePathRegExp, params['path'])
        if matches:
            source = self.contentDirectory / matches.group(1) / matches.group(4) / matches.group(5)
            dest = self.contentDirectory / matches.group(5)
            if os.path.exists(source) and not os.path.exists(dest):
                shutil.copy(source, dest)

            params['path'] = matches.group(5)
        else:
            oldPath = self.basePath / editorPath / Path(params['path'])
            newPath = self.basePath / self.contentDirectory / params['path']
            if not os.path.exists(newPath) and os.path.exists(oldPath):
                shutil.copy(oldPath, newPath)

        files.append(params['path'])

    ##
    # This function will prefix all paths within a css file.
    ##
    def buildCssPath(self, matches, base=None):
        global buildBase
        if base is not None:
            buildBase = base

        if matches is None:
            return

        dirr = re.sub('(css/|styles/|Styles/|Css/)', 'fonts/', buildBase)
        path = dirr + matches.group(1)

        return 'url(' + path + ')'

    ##
    # Parses library data from a string on the form {machineName} {majorVersion}.{minorVersion}
    ##
    def libraryFromString(self, libraryString):
        pre = '^([\w0-9\-\.]{1,255})[\-\ ]([0-9]{1,5})\.([0-9]{1,5})$'
        res = re.search(pre, libraryString)
        if res:
            return {'machineName': res.group(1), 'majorVersion': res.group(2), 'minorVersion': res.group(3)}
        return False
