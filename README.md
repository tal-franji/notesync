# notesync
Note sync aims to allow synchronizing python project files from your laptop (e.g. PyCharm) to a hosted notebook service (e.g. Google Colab)

## Jupyter
[Jupyter](https://jupyter.org/) is a web interface for working interactivly with code. Used by python developpers (and other languages). Very common tool for data-scientists.

## Hosted notebooks
Many cloud providers allwo running interactive code on cluster of computers for analysis, big-data and deep-learning.
Tools such as Google Colab, Databricks notebooks, Amazon SageMaker etc. Many companies use notebooks as their primary tools for hadling data (for example [Netflix](https://www.dataengineeringpodcast.com/using-notebooks-as-the-unifying-layer-for-data-roles-at-netflix-with-matthew-seal-episode-54/) )
### challenges with hosted notebooks
When working with hosted notebooks (either cloud or enteprise) things get complicated when code gets more complex.
When user wants to move functions and classes into her own modules and libraries - working in a notebook can be limiting.
Developers' IDE for python are build for building complex code projects with refactoring, testing and debugging capabilities.

However there is no easy way to move your own code/library to the hosted notebook machine. Even more so when you are working and modifiying these libraries as you go.

There is no easy network connection between the machine hosting the notebook and the developper's notebook - notebook machine is behind a firewall/proxy etc.

## notesync design
The design of notesync involves 3 components
1. server running on the laptop looking at the source directory and tracking changed files
2. Code running in the notebook under the ipython API - combinatiuon of JavaScript and python - the code connect via JavaScript to the user's laptop to get changes and then run python code (which executes on the notebook machine) to write the update
3. process running on the notebook machine - taking changes and applying them to the local copy of the files.

## References
Dirsync is an older tool used to sync via external proxy service 'ngrok' [dirsync](https://github.com/tal-franji/miscutil/blob/master/dirsync2.py)
dirsync.py operates differently - an http server runs on the notebook machine and the client is on the laptop.

calling python from JavaScript in [Jupyter](https://jakevdp.github.io/blog/2013/06/01/ipython-notebook-javascript-python-communication/)

Google Colab is a variant of Jupyter with a modified API. 
callin python from JavaScript in [Google Colab](
https://colab.research.google.com/notebooks/snippets/advanced_outputs.ipynb#scrollTo=SQM0MFHc6vPI)





