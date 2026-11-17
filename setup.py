import distutils.cmd
import pathlib
import re
import sys

from setuptools import find_packages, setup


PACKAGE_NAME = 'leadbombing'
ROOT_DIR = pathlib.Path(__file__).parent
VERSION_PATH = ROOT_DIR / PACKAGE_NAME / 'version.py'
README_PATH = ROOT_DIR / 'README.md'

long_description = README_PATH.read_text(encoding='utf-8')
long_description_content_type = 'text/markdown'

match = re.search(r'^version\s*=\s*[\'"](?P<version>.+?)[\'"]',
                  VERSION_PATH.read_text(encoding='utf-8'), re.M)
assert match
version = match.group('version')


class BuildStandaloneCommand(distutils.cmd.Command):
    """A custom command to build standalone app."""
    description = 'Build standalone app with PyInstaller'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import os
        import shutil
        import subprocess
        import sys

        try:
            # Target filename
            dist_filename = 'LeadBombing'

            # Dist
            build_cmd = [
                'pyinstaller',
                '--clean',
                '--onefile',
                '--windowed',
                '-n', dist_filename,
            ]

            # Icon
            if sys.platform.startswith('win'):
                build_cmd += [
                    '--icon', 'leadbombing/data/images/icon.ico',
                ]
            elif sys.platform.startswith('darwin'):
                build_cmd += [
                    '--icon', 'leadbombing/data/images/icon.icns',
                ]

            # Add data (reference data + bundled web dashboard assets).
            # The web UI is served from leadbombing/web/static, so it must be
            # frozen into the binary or the dashboard 404s.
            build_cmd += [
                '--add-data', f'leadbombing/data{os.pathsep}leadbombing/data',
                '--add-data', f'leadbombing/web{os.pathsep}leadbombing/web',
                'leadbombing.py',
            ]

            print('Running command: %s' % ' '.join(build_cmd), file=sys.stderr)
            subprocess.check_call(build_cmd)
        finally:
            # Cleanup
            shutil.rmtree(ROOT_DIR / 'build', ignore_errors=True)
            try:
                os.remove(ROOT_DIR / f'{dist_filename}.spec')
            except FileNotFoundError:
                pass


if __name__ == '__main__':
    setup(
        name='leadbombing',
        version=version,
        description='LeadBombing: локальный поиск лидов в 2ГИС',
        long_description=long_description,
        long_description_content_type=long_description_content_type,
        author='Egor Drozd',
        packages=find_packages(include=[PACKAGE_NAME, f'{PACKAGE_NAME}.*']),
        include_package_data=True,
        python_requires='>=3.8',
        keywords='leads 2gis',
        url='https://github.com/Wasaby3/LeadBombing',
        install_requires=[
            'pychrome>=0.2.4',
            'pydantic>=2.0,<3.0',
            'psutil>=5.4.8',
            'requests>=2.13.0',
            'xlsxwriter>=3.0.5',
            'Flask>=2.2',
        ],
        extras_require={
            'dev': [
                'pyinstaller>=6.6.0',
                'pytest>=7.0',
                'tox>=4',
                'pre-commit>=3',
                'wheel>=0.40',
            ],
        },
        classifiers=[
            "Topic :: Internet",
            "Topic :: Utilities",
            "Operating System :: OS Independent",
            "Programming Language :: Python :: 3 :: Only",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "Programming Language :: Python :: 3.13",
            "Natural Language :: Russian",
            "Intended Audience :: End Users/Desktop",
            "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)",
        ],
        license='LGPLv3+',
        entry_points={'console_scripts': [
            'leadbombing = leadbombing.web:main',
            'leadbombing-cli = leadbombing:main',
        ]},
        cmdclass={'build_standalone': BuildStandaloneCommand}
    )
