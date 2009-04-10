from mitterlib.constants import version

params = {
        'name': 'mitter',
        'version': version,
        'description': 'Update your Twitter status',
        'author': 'Julio Biason',
        'author_email': 'julio@juliobiason.net',
        'url': 'http://code.google.com/p/mitter/',
        'scripts': ['mitter'],
        'packages': [
            'mitterlib',
            'mitterlib.ui'],
        'data_files': [
            ('share/pixmaps', 
                ['pixmaps/mitter.png',
                 'pixmaps/mitter-new.png',
                 'pixmaps/unknown.png'])],
        'license': 'GPL3',
        'download_url': \
            'http://mitter.googlecode.com/files/mitter-%s.tar.gz' % (version),
        'classifiers': [
            'Development Status :: 4 - Beta',
            'Environment :: Console',
            'Environment :: X11 Applications :: GTK',
            'Intended Audience :: End Users/Desktop',
            'License :: OSI Approved :: GNU General Public License (GPL)',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
            'Topic :: Communications :: Chat']}

from distutils.core import setup

# this bit should be the same for both systems
setup(**params)
