from setuptools import setup
import sys

extra = {}
if sys.version_info >= (3,):
    extra['use_2to3'] = True

setup(
    name = 'microdata',
    version = '0.6.1',
    description = "html5lib extension for parsing microdata",
    author = "Ed Summers",
    author_email = "ehs@pobox.com",
    url = "http://github.com/edsu/microdata",
    py_modules = ['microdata'],
    scripts = ['microdata.py'],
    test_suite = 'test',
    install_requires = [
        'w3lib>=1.1',
        'lxml>=3.6.4',
    ],
    **extra
)
