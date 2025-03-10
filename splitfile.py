import logging
import traceback
import dateutil.parser
import pytz  # pip install pytz
import os
import shutil
import time
import json
import re

from processor.EntryProcessor import EntryProcessor
from processor.PdfEntryProcessor import PdfEntryProcessor
from processor.PhotoEntryProcessor import PhotoEntryProcessor
from config.config import Config


def rename_media(root, subpath, media_entry, filetype):
    pfn = os.path.join(root, subpath, "%s.%s" % (media_entry["md5"], filetype))
    if os.path.isfile(pfn):
        newfn = os.path.join(
            root, subpath, "%s.%s" % (media_entry["identifier"], filetype)
        )
        print("Renaming %s to %s" % (pfn, newfn))
        os.rename(pfn, newfn)


# Load the configuration
Config.load_config("config.yaml")
DEFAULT_TEXT = Config.get("DEFAULT_TEXT", "")

# Initialize the EntryProcessor class variables
EntryProcessor.initialize()

# Set this as the location where your Journal.json file is located
root = Config.get("ROOT")
icons = False  # Set to true if you are using the Icons Plugin in Obsidian

# name of folder where journal entries will end up
journalFolder = os.path.join(root, Config.get("JOURNAL_FOLDER"))
fn = os.path.join(root, Config.get("JOURNAL_JSON"))

# Clean out existing journal folder, otherwise each run creates new files
if os.path.isdir(journalFolder):
    print("Deleting existing folder: %s" % journalFolder)
    shutil.rmtree(journalFolder)
# Give time for folder deletion to complete. Only a problem if you have the folder open when trying to run the script
time.sleep(2)

if not os.path.isdir(journalFolder):
    print("Creating journal folder: %s" % journalFolder)
    os.mkdir(journalFolder)

if icons:
    print("Icons are on")
    dateIcon = "`fas:CalendarAlt` "
else:
    print("Icons are off")
    dateIcon = ""  # make 2nd level heading

print("Begin processing entries")
count = 0
with open(fn, encoding="utf-8") as json_file:
    data = json.load(json_file)

    photo_processor = PhotoEntryProcessor()
    pdf_processor = PdfEntryProcessor()

    for entry in data["entries"]:
        newEntry = []

        createDate = dateutil.parser.isoparse(entry["creationDate"])
        localDate = createDate.astimezone(
            pytz.timezone(entry["timeZone"])
        )  # It's natural to use our local date/time as reference point, not UTC

        # Format the date and time with the weekday
        formatted_datetime = createDate.strftime("%Y-%m-%d %H:%M:%S %A")

        dateCreated = formatted_datetime
        coordinates = ""

        frontmatter = f"---\n" f"date: {dateCreated}\n"

        weather = EntryProcessor.get_weather(entry)
        if len(weather) > 0:
            frontmatter += f"weather: {weather}\n"
        tags = EntryProcessor.get_tags(entry)
        if len(tags) > 0:
            frontmatter += f"tags: {tags}\n"

        if "location" in entry:
            coordinates = EntryProcessor.get_coordinates(entry)

        frontmatter += "locations: \n"
        frontmatter += "---\n"

        newEntry.append(frontmatter)

        # If you want time as entry title, uncomment below.
        # Add date as page header, removing time if it's 12 midday as time obviously not read
        # if sys.platform == "win32":
        #     newEntry.append(
        #         '## %s%s\n' % (dateIcon, localDate.strftime("%A, %#d %B %Y at %#I:%M %p").replace(" at 12:00 PM", "")))
        # else:
        # newEntry.append('## %s%s\n' % (
        #     dateIcon, localDate.strftime("%A, %-d %B %Y at %-I:%M %p").replace(" at 12:00 PM", "")))  # untested

        # Add body text if it exists (can have the odd blank entry), after some tidying up
        try:
            if "text" in entry:
                newText = entry["text"].replace("\\", "")
            else:
                newText = DEFAULT_TEXT
            newText = newText.replace("\u2028", "\n")
            newText = newText.replace("\u1c6a", "\n\n")

            if "photos" in entry:
                # Correct photo links. First we need to rename them. The filename is the md5 code, not the identifier
                # subsequently used in the text. Then we can amend the text to match. Will only to rename on first run
                # through as then, they are all renamed.
                # Assuming all jpeg extensions.
                photo_list = entry["photos"]
                for p in photo_list:
                    photo_processor.add_entry_to_dict(p)
                    rename_media(root, "photos", p, p["type"])

                # Now to replace the text to point to the file in obsidian
                newText = re.sub(
                    r"(\!\[\]\(dayone-moment:\/\/)([A-F0-9]+)(\))",
                    photo_processor.replace_entry_id_with_info,
                    newText,
                )

            if "pdfAttachments" in entry:
                pdf_list = entry["pdfAttachments"]
                for p in pdf_list:
                    pdf_processor.add_entry_to_dict(p)
                    rename_media(root, "pdfs", p, p["type"])

                newText = re.sub(
                    r"(\!\[\]\(dayone-moment:\/pdfAttachment\/)([A-F0-9]+)(\))",
                    pdf_processor.replace_entry_id_with_info,
                    newText,
                )

            newEntry.append(newText)

        except Exception as e:
            logging.error(f"Exception: {e}")
            logging.error(traceback.format_exc())
            pass

        ## Start Metadata section

        newEntry.append("\n\n---\n")

        # Add location
        location = EntryProcessor.get_location_coordinate(entry)
        if not location == "":
            newEntry.append(location)

        # Save entries organised by year, year-month, year-month-day.md
        yearDir = os.path.join(journalFolder, str(createDate.year))
        monthDir = os.path.join(yearDir, createDate.strftime("%m"))

        if not os.path.isdir(yearDir):
            os.mkdir(yearDir)

        if not os.path.isdir(monthDir):
            os.mkdir(monthDir)

        # To be compatible with Obsidian's Daily Notes plugin, we want
        # YYYY/MM/YYYY-MM-DD.md
        fnNew = os.path.join(monthDir, "%s.md" % (localDate.strftime("%Y-%m-%d")))

        # Here is where we handle multiple entries on the same day. Each goes to it's own file
        if os.path.isfile(fnNew):
            # File exists, need to find the next in sequence and append alpha character marker
            index = 97  # ASCII a
            fnNew = os.path.join(
                monthDir,
                "%s %s.md" % (localDate.strftime("%Y-%m-%d"), chr(index)),
            )
            while os.path.isfile(fnNew):
                index += 1
                fnNew = os.path.join(
                    monthDir,
                    "%s %s.md" % (localDate.strftime("%Y-%m-%d"), chr(index)),
                )

        with open(fnNew, "w", encoding="utf-8") as f:
            for line in newEntry:
                f.write(line)

        count += 1

print("Complete: %d entries processed." % count)
