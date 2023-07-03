import csv
import os
from datetime import datetime, timedelta

INPUT_DATE_FORMAT = "%Y-%m-%d_%H.%M.%S"
OUTPUT_DATE_FORMAT = "%Y-%m-%d_%H.%M.%S"
OUTPUT_PATH_DATE_FORMAT = "%Y%m%d_%H%M%S"
PEDAL_THRESHOLD = 80.0
MIN_PEDAL_FOR_WOT = 99.0
OUTPUT_FOLDER = "output_temp"
OUTPUT_PREFIX = "BATCH_"
GROUP_WOT = False

USE_EXISTING_OUTPUT_PATH = True


class DS2LogReader:
    def __init__(
        self,
        input_date_format=None,
        output_date_format=None,
        output_path_date_format=None,
        pedal_threshold=None,
        mid_pedal_for_wot=None,
        output_folder=None,
        output_prefix=None,
        group_wot=None,
    ):
        self.input_date_format = (
            input_date_format if input_date_format else INPUT_DATE_FORMAT
        )
        self.output_date_format = (
            output_date_format if output_date_format else OUTPUT_DATE_FORMAT
        )
        self.output_path_date_format = (
            output_path_date_format
            if output_path_date_format
            else OUTPUT_PATH_DATE_FORMAT
        )
        self.pedal_threshold = (
            pedal_threshold if pedal_threshold else PEDAL_THRESHOLD
        )
        self.mid_pedal_for_wot = (
            mid_pedal_for_wot if mid_pedal_for_wot else MIN_PEDAL_FOR_WOT
        )
        self.output_folder = output_folder if output_folder else OUTPUT_FOLDER
        self.output_prefix = output_prefix if output_prefix else OUTPUT_PREFIX

        self.group_wot = group_wot if group_wot else GROUP_WOT

        self.batch_start_time = None
        self.output_path_created = False
        self.output_path = ""
        self.file_list = []

    def process_file(self, filepath):
        # If this is the first file in the batch, create batch_start_time
        if not self.batch_start_time:
            self.batch_start_time = datetime.now()
            result = self.create_output_folders()
            if result != "":
                return result

        file_basename = os.path.basename(filepath)

        with open(filepath, "r") as file:
            # this does not allow flexible input formats
            if file_basename == "ds1.csv":
                in_datetime = datetime
                pedal_header = "Pedal(%)"
                eth_header = "Ethanol(%)"
                gear_header = "Gear(-)"
                map_header = "Map switch(-)"
                time_header = "Time(s)"
            else:
                in_datetime = datetime.strptime(
                    file_basename.split("_log.csv")[0], self.input_date_format
                )
                pedal_header = "Pedal(wped_w)(% PED)"
                eth_header = "Ethanol cont(ethanolpercent)(%)"
                gear_header = "Gear(gangi)()"
                map_header = "Map switch(mapswitch)(raw)"
                time_header = "Time(s)"

            reader = csv.reader(file)
            title = next(reader)  # get the title line
            headers = next(reader)  # get the headers line

            # get the indexes for various relevent columns
            # this may need to be altered to allow flexible thresholding
            index = headers.index(pedal_header)
            eth_index = headers.index(eth_header)
            gear_index = headers.index(gear_header)
            map_index = headers.index(map_header)
            time_index = headers.index(time_header)

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

                # TODO: Create setting to allow misformed data
                if line[index] == "":
                    return ""
                if float(line[index]) >= self.pedal_threshold:
                    # this ensures its a WOT run - could use some refining because it.. doesn't
                    if float(line[index]) >= self.mid_pedal_for_wot:
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
                filtered_sets.append((meta_data, current_set))

        return self.write_sets(
            title=title,
            headers=headers,
            filtered_sets=filtered_sets,
            # filtered_headers=[
            #     "Time(s)",
            #     "Ign earliest poss(zwbas)(Grad KW)",
            #     "Eng spd(nmot_w)(1/min)",
            # ],
        )

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
            error_msg = f"ERROR: Output path {self.output_path} already exists. Allowing this can be changed in settings"
            print(error_msg)
            return error_msg
        elif not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        self.output_path_created = True

        return ""

    def write_sets(self, title, headers, filtered_sets, filtered_headers=[]):
        if not self.output_path_created:
            error_msg = "ERROR: Output folders have not been initialized"
            print(error_msg)
            return error_msg

        if filtered_headers == []:
            filtered_headers = headers

        header_indices = [headers.index(fh) for fh in filtered_headers]

        if not self.group_wot:
            return self.write_as_individuals(
                title, filtered_headers, filtered_sets, header_indices
            )

        else:
            return self.write_as_one(
                title, filtered_headers, filtered_sets, header_indices
            )

        return ""

    def write_as_individuals(
        self, title, filtered_headers, filtered_sets, header_indices
    ):
        # write each set of lines to a separate file
        for i, filtered_set in enumerate(filtered_sets):
            meta_data = filtered_set[0]
            lines = filtered_set[1]

            time_output = meta_data["set_start"].strftime(
                self.output_date_format
            )
            filename = f"{time_output}_G{''.join(meta_data['gears'])}_E{meta_data['eth']}_M{meta_data['map']}.csv"
            output_filename = os.path.join(self.output_path, filename)

            with open(output_filename, "w", newline="") as output_file:
                writer = csv.writer(output_file)
                writer.writerow(title)  # write the title line
                writer.writerow(
                    filtered_headers
                )  # write the filtered headers line
                writer.writerows(
                    [line[i] for i in header_indices] for line in lines
                )  # write the filtered lines to the output file

        return ""

    def write_as_one(
        self, title, filtered_headers, filtered_sets, header_indices
    ):
        time_index = filtered_headers.index("Time(s)")

        if len(filtered_sets) == 0:
            return ""

        filename = (
            filtered_sets[0][0]["set_start"].strftime(self.output_date_format)
            + "_combined.csv"
        )
        output_filename = os.path.join(self.output_path, filename)
        with open(
            output_filename,
            "w",
            newline="",
        ) as output_file:
            writer = csv.writer(output_file)
            writer.writerow(title)
            writer.writerow(filtered_headers)
            end_time = 0.0
            for filtered_set in filtered_sets:
                offset = float(filtered_set[1][0][time_index]) - end_time
                for row in filtered_set[1]:
                    row[time_index] = str(
                        round(float(row[time_index]) - offset, 3)
                    )
                    end_time = float(row[time_index])
                    writer.writerow([row[i] for i in header_indices])
                for i in range(20):
                    end_time += 0.05
                    row = [str(round(end_time))] + ["0"] * (
                        len(filtered_headers) - 1
                    )
                    writer.writerow(row)
                end_time += 0.05

        return ""


def get_unique_files(dir):
    unfiltered_files = set(os.listdir(dir))
    filtered_files = []

    for file in unfiltered_files:
        if os.path.isdir(os.path.join(dir, file)):
            filtered_files += [
                os.path.join(file, f)
                for f in os.listdir(os.path.join(dir, file))
            ]
        else:
            filtered_files.append(file)

    filtered_files = set(filtered_files)
    return filtered_files
