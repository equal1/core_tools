# Core-tools
Core-tools is a light-weight dataset that supports common spin-qubit measurement practices. 
It features a local data storage solution, as well as tools for remote storage.

## Documentation
Core-tools documentation can be found in a couple of different locations.

### Configuration
For users associated with QuTech or the TU Delft, there are wiki-pages documenting how to set up a measurement environment using core-tools.

These pages are located on the [QDLabs GitLab wiki](https://gitlab.tudelft.nl/qutech-qdlabs/measurement-systems/documentation/-/wikis/home).
To get started, have a look at the following pages: 'laptop/measurement-pc software
installation', 'core-tools configuration', 'using sqdl' and 'gitlab credentials'.

### Project
Project documentation can be found as a set of markdown files in the ```docs/source``` directory, starting with ```docs/source/index.rst```.

For convenience, it is possible to compile these documents into a set of HTML files that you can read in your browser.

On Windows:
```bat
.\.venv\Scripts\activate
pip install sphinx
cd docs/
make.bat html
```

On Linux:
```bash
source .venv/bin/activate
pip install sphinx 
cd docs/
make html
```

You can now access the documentation by opening ```docs/build/html/index.html``` in your web-browser of choice.

