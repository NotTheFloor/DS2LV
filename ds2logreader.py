import csv
import os
import json
from datetime import datetime, timedelta

INPUT_DATE_FORMAT = "%Y-%m-%d_%H.%M.%S"
OUTPUT_DATE_FORMAT = "%Y-%m-%d_%H.%M.%S"
OUTPUT_PATH_DATE_FORMAT = "%Y%m%d_%H%M%S"
PEDAL_THRESHOLD = 80.0
MIN_PEDAL_FOR_MAX = 99.0
OUTPUT_FOLDER = "output_temp"
OUTPUT_PREFIX = "BATCH_"
AUTO_RUN = True

IGNORE_SUB_FOLDERS = True
IGNORE_NON_CSV = True
USE_EXISTING_OUTPUT_PATH = True


class DS2LogReader:
    def __init__(
        self,
        input_path=None,
        input_date_format=INPUT_DATE_FORMAT,
        output_date_format=OUTPUT_DATE_FORMAT,
        output_path_date_format=OUTPUT_PATH_DATE_FORMAT,
        pedal_threshold=PEDAL_THRESHOLD,
        min_pedal_for_max=MIN_PEDAL_FOR_MAX,
        output_folder=OUTPUT_FOLDER,
        output_prefix=OUTPUT_PREFIX,
        auto_run=AUTO_RUN,
    ):
        self.input_path = input_path
        self.input_date_format = input_date_format
        self.output_date_format = output_date_format
        self.output_path_date_format = output_path_date_format
        self.pedal_threshold = pedal_threshold
        self.min_pedal_for_max = min_pedal_for_max
        self.output_folder = output_folder
        self.output_prefix = output_prefix

        self.batch_start_time = None
        self.output_path_created = False
        self.output_path = ""
        self.file_list = []

        if input_path:
            self.create_file_list(input_path)
            if auto_run:
                self.process_file_list()

    def process_file(self, filepath, debug=True):
        if not self.batch_start_time:
            self.batch_start_time = datetime.now()
            if debug:
                print(f"Creating output folder")
            self.create_output_folders()

        if debug:
            print(f"Processing file {filepath}")

        file_basename = os.path.basename(filepath)

        if debug:
            print(f"File basename {file_basename}")

        with open(filepath, "r") as file:
            # this does not allow flexible input formats
            in_datetime = datetime.strptime(
                file_basename.split("_log.csv")[0], self.input_date_format
            )

            reader = csv.reader(file)
            title = next(reader)  # get the title line
            headers = next(reader)  # get the headers line

            # get the indexes for various relevent columns
            # this may need to be altered to allow flexible thresholding
            index = headers.index("Pedal(wped_w)(% PED)")
            eth_index = headers.index("Ethanol cont(ethanolpercent)(%)")
            gear_index = headers.index("Gear(gangi)()")
            map_index = headers.index("Map switch(mapswitch)(raw)")
            time_index = headers.index("Time(s)")

            # Initial data for loop
            meta_data = {"map": -1, "eth": -1, "gears": [], "set_start": None}
            hits_max_threshold = False

            # iterate through the lines and group them into sets of contiguous lines that meet the criteria
            filtered_sets = []
            current_set = []
            for line in reader:
                # Polling rate for map is low, so we check if its there, and record it
                if line[map_index]:
                    meta_data["map"] = str(int(float(line[map_index])))
                if line[eth_index]:
                    meta_data["eth"] = str(int(round(float(line[eth_index]))))

                if float(line[index]) >= self.pedal_threshold:
                    # this ensures its a WOT run - could use some refining because it.. doesn't
                    if float(line[index]) >= self.min_pedal_for_max:
                        hits_max_threshold = True
                    if line[gear_index]:
                        # checks for kickdown and if so  ignores initial gear
                        if len(meta_data["gears"]) == 1:
                            if meta_data["gears"][0] > line[gear_index]:
                                meta_data["gears"] = []
                        if line[gear_index] not in meta_data["gears"]:
                            meta_data["gears"].append(line[gear_index])
                    if not current_set:
                        meta_data["set_start"] = in_datetime + timedelta(
                            seconds=int(float(line[time_index]))
                        )

                    current_set.append(line)
                elif current_set:
                    if hits_max_threshold:
                        hits_max_threshold = False
                        filtered_sets.append((meta_data, current_set))
                    current_set = []
                    # Full reset is required
                    meta_data = {
                        "map": meta_data["map"],
                        "eth": meta_data["eth"],
                        "gears": [],
                        "set_start": None,
                    }
            if current_set:
                print("**** ADDING")
                filtered_sets.append((meta_data, current_set))

        if debug:
            print(f"Writing filtered_sets {len(filtered_sets)}")

        self.write_sets(
            title=title, headers=headers, filtered_sets=filtered_sets
        )

        print("Returning all good")
        return ""

    def create_output_folders(self):
        if self.output_path_created:
            return

        # set up output format and create folders if needed
        output_suffix = self.batch_start_time.strftime(
            self.output_path_date_format
        )
        self.output_path = os.path.join(
            self.output_folder, self.output_prefix + output_suffix
        )

        if os.path.exists(self.output_path) and not USE_EXISTING_OUTPUT_PATH:
            print(
                f"ERROR: Output path {output_path} already exists. Allowing this can be changed in settings"
            )
            input("Press any key to continue...")
            quit()
        elif not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        self.output_path_created = True

    def write_sets(self, title, headers, filtered_sets):
        if not self.output_path_created:
            print("ERROR: Output folders have not been initialized")
            input("Press any key to continue...")
            quit()

        # write each set of lines to a separate file
        for i, filtered_set in enumerate(filtered_sets):
            meta_data = filtered_set[0]
            lines = filtered_set[1]

            time_output = meta_data["set_start"].strftime(
                self.output_date_format
            )
            filename = f"{time_output}_G{''.join(meta_data['gears'])}_E{meta_data['eth']}_M{meta_data['map']}.csv"
            output_filename = os.path.join(self.output_path, filename)
            print(output_filename)
            with open(output_filename, "w", newline="") as output_file:
                writer = csv.writer(output_file)
                writer.writerow(title)  # write the title line
                writer.writerow(headers)  # write the headers line
                writer.writerows(
                    lines
                )  # write the filtered lines to the output file

    def create_file_list(self, path):
        if not os.path.exists(path):
            print(f"ERROR: Path {path} does not exist")
            input("Press any key to continue...")
            quit()

        if os.path.isfile(path):
            self.file_list.append(path)
        elif os.path.isdir(path):
            self.file_list = [
                os.path.join(path, name) for name in os.listdir(path)
            ]
        else:
            print(f"ERROR: Path {path} is neither a file nor directory")
            input("Press any key to continue...")
            quit()

    def process_file_list(self):
        if not self.file_list:
            print(f"WARNING: Attempted to process empty file list")
            input("Press any key to continue...")
            return

        for filename in self.file_list:
            if os.path.isdir(filename):
                if IGNORE_SUB_FOLDERS:
                    print(f"WARNING: Non .csv {filename} is in batch")
                    continue
                else:
                    print(
                        f"ERROR: {filename} is a directory. Sub directories can be ignored within settings"
                    )
                    input("Press any key to continue...")
                    quit()
            elif filename[-4:] != ".csv":
                if IGNORE_NON_CSV:
                    print(f"WARNING: Non .csv {filename} is in batch")
                    continue
                else:
                    print(
                        f"ERROR: File {filename} is not a csv file. Non-csv files can be processed by changing the settings"
                    )
                    input("Press any key to continue...")
                    quit()
            elif not os.path.isfile(filename):
                print(f"ERROR: {filename} is not a file or a directory")
                input("Press any key to continue...")
                quit()

            self.process_file(filename)


def get_unique_files(dir):
    unfiltered_files = set(os.listdir(dir))
    print("Unfiltered files")
    print(json.dumps(list(unfiltered_files), indent=2))
    filtered_files = []

    for file in unfiltered_files:
        print(f"Check: {file}")
        if os.path.isdir(os.path.join(dir, file)):
            print(f"{file} is a directory")
            filtered_files += [
                os.path.join(file, f)
                for f in os.listdir(os.path.join(dir, file))
            ]
        else:
            print(f"{file} is NOT a directory")
            filtered_files.append(file)

    print("Filtered files")
    print(json.dumps(list(filtered_files), indent=2))

    return set(filtered_files)
