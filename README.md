# Scholar pls stop
Tired of receiving google scholar recommendations for papers I've already read, this tool filters duplicate and already-read papers through a local blacklist or your Zotero library.

## Setup
You're gonna need:
- a Google account
- a Zotero library (optional)

Setup a [Google app](https://developers.google.com/gmail/api/quickstart/python), and run `quickstart.py` to get local credentials (`token.json`).
Credentials are only temporary, so from time to time you may need to run the script again.
Write down the label of your Google Scholar emails, you're gonna need to only read those emails.

## Run
You can run from the command line or from a python shell:
```
python3 scholar.py --email=john.doe@gmail.com --zotero_id=XXXXXXX --zotero_key=XXXXXXXXXXXXXXXXXXXXXXXXX --blacklist
```
The `--blacklist` flag adds the new papers to a blacklist (file `blacklist_papers.list`) so that they won't be shown again **regardless of the Zotero database**.


## Blacklists
Papers can be blacklisted through a `blacklist_papers.list` file, which is a plain-text file in which on each line is the title of a paper to ignore.
This file is updated at each run of the script **if and only if the `blacklist` flat is used**.

## Zotero DB
Optionally, you can use your Zotero library as an automatic filter for already-read papers.
To generate your library DB just run the script as detailed above, specifying your library ID and a [Zotero development key](https://www.zotero.org/settings/keys/new).
