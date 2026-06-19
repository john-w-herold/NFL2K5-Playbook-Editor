from psu.psu import PSU
import zlib, struct
import csv

# --- Formation Object ---
class Formation:
    def __init__(self, name, side, package=None, starting_address=None):
        self.name = name
        self.side = side
        self.package = package
        self.starting_address = starting_address
        self.play_bytes = []
        self.plays = []

    def __repr__(self):
        return f"Formation(name={self.name!r}, side={self.side!r}, package={self.package!r}, starting_address={hex(self.starting_address)}, plays={self.plays}, play_bytes={self.play_bytes})"

class PB_PSU:
    #PLAYBOOK_ADDRESS = 0x245C
    PLAYBOOK_ADDRESS = 0x2458
    PLAYBOOK_END = 0x33F7
    STRING_TABLE_START = 0x10840
    FF_SENTINEL = (0xFF, 0x01)
    
    def __init__(self, file_name):
        self.file_name = file_name
        self.psu = PSU.load(self.file_name)
        self.psu_name = None
        self.temp_name = "TempDir"
        for entry in self.psu.list():
            if entry.isDirectory():
                if entry.name in (".", ".."):
                    continue
                if self.psu_name:
                    raise ValueError("Multiple directory names found")
                self.psu_name = entry.name
                entry.name = self.temp_name
        file_bytes = self.psu.read(self.psu_name)
        self.file_bytes_array = bytearray(file_bytes)

        self.playbook_formations = {}
        self.all_playbook_plays = set()
        self.index_to_formation_name = {}
        self.index_to_package_name = {}
        self.index_to_play_name = {}
        self.formation_name_to_index = {}
        self.package_name_to_index = {}
        self.play_name_to_index = {}
        self.blocks = []

    def save_psu(self):
        file_bytes = bytes(self.file_bytes_array)
        self.psu.write(self.psu_name, file_bytes)

        # Update Extra 
        crc = zlib.crc32(file_bytes) & 0xFFFFFFFF
        self.psu.write('EXTRA', struct.pack('<I', crc))


        # Change directory name back
        for entry in self.psu.list():
            if entry.isDirectory():
                if entry.name == self.temp_name:
                    entry.name = self.psu_name
        self.psu.save()

        # Reload PSU to reset internal pypsu state for subsequent saves
        self.psu = PSU.load(self.file_name)
        for entry in self.psu.list():
            if entry.isDirectory():
                if entry.name in (".", ".."):
                    continue
                self.psu_name = entry.name
                entry.name = self.temp_name


    def write_formation_to_bytes(self, formation):
        i = formation.starting_address + 4
        for play in formation.play_bytes:
            self.file_bytes_array[i] = play[0]
            self.file_bytes_array[i+1] = play[1]
            i+=2

        # Fill remaining play slots with FF sentinel up to package row
        package_row_address = formation.starting_address + 76
        while i < package_row_address:
            self.file_bytes_array[i] = PB_PSU.FF_SENTINEL[0]
            self.file_bytes_array[i+1] = PB_PSU.FF_SENTINEL[1]
            i += 2

    # --- 1. Parse String Table for Formation and Package Name Indexes ---
    def parse_string_table(self, formation_names, package_names, play_names):
        """
        Scans the string table sequentially from start.
        For each UTF-16 LE null-terminated string found, determines if it is a
        formation name, package name, or other (play name etc).
        First occurrence of a name in formation_names = formation.
        If that name also appears in package_names, second occurrence = package.
        If a name only appears in package_names, first occurrence = package.
        Returns:
            index_to_formation_name: dict of string_table_index -> formation name
            index_to_package_name: dict of string_table_index -> package name
        """
        formation_seen = set() # See if we already have a formation; if so, check if it's a package
        package_seen = set() # See if we already have a package; if so, check if it's a play
        self.index_to_formation_name = {}
        self.index_to_package_name = {}
        self.index_to_play_name = {}
        formation_idx = 0
        package_idx = 0
        play_idx = 0

        i = PB_PSU.STRING_TABLE_START
        while i < len(self.file_bytes_array) - 1:
            # Read until null terminator (00 00)
            j = i
            while j + 1 < len(self.file_bytes_array):
                if self.file_bytes_array[j] == 0x00 and self.file_bytes_array[j + 1] == 0x00:
                    break
                j += 2
            raw = self.file_bytes_array[i:j]
            if len(raw) == 0:
                i = j + 2
                continue
            try:
                s = raw.decode('utf-16-le')
            except UnicodeDecodeError:
                i = j + 2
                continue

            if s in formation_names and s not in formation_seen:
                formation_seen.add(s)
                self.index_to_formation_name[formation_idx] = s
                formation_idx += 1
            elif s in package_names and s not in package_seen:
                package_seen.add(s)
                self.index_to_package_name[package_idx] = s
                package_idx += 1
            elif s in play_names:
                self.index_to_play_name[play_idx] = s
                play_idx += 1

            i = j + 2

    def change_package(self, formation, package_index):
        package_address = formation.starting_address + 76
        self.file_bytes_array[package_address] = package_index

    # --- 2. Detect Block Starting Addresses ---
    def get_blocks(self):
        BLOCK_SIZE = 80  # 40 rows * 2 bytes
        PLAY_ROW_START = 4  # skip first 2 rows (4 bytes)
        PLAY_ROW_END = 76  # up to row 38 (76 bytes), rows 3-38
        PACKAGE_ROW = 76  # row 39 starts at byte 76

        self.blocks = []
        i = PB_PSU.PLAYBOOK_ADDRESS
        while i + BLOCK_SIZE <= PB_PSU.PLAYBOOK_END:
            block_start = i
            # Skip block if first play row is null
            if self.file_bytes_array[block_start + PLAY_ROW_START] == 0x00 and \
               self.file_bytes_array[block_start + PLAY_ROW_START + 1] == 0x00:
                i += BLOCK_SIZE
                continue
            rows = []

            # Read play rows (rows 3-38)
            for offset in range(PLAY_ROW_START, PLAY_ROW_END, 2):
                b0 = self.file_bytes_array[block_start + offset]
                b1 = self.file_bytes_array[block_start + offset + 1]
                if b0 == PB_PSU.FF_SENTINEL[0] and b1 == PB_PSU.FF_SENTINEL[1]:
                    break
                rows.append((b0, b1))

            # Read package row (row 39)
            pkg_b0 = self.file_bytes_array[block_start + PACKAGE_ROW]
            pkg_b1 = self.file_bytes_array[block_start + PACKAGE_ROW + 1]
            rows.append((pkg_b0, pkg_b1))

            self.blocks.append((block_start, rows))
            i += BLOCK_SIZE

    def load_playbook(self, formations, package_names, play_names):
        self.parse_string_table(formations.keys(), package_names, play_names)

        # Build reverse lookup: string table index -> name
        self.formation_name_to_index = {v: k for k, v in self.index_to_formation_name.items()}
        self.package_name_to_index = {v: k for k, v in self.index_to_package_name.items()}
        self.play_name_to_index = {v: k for k, v in self.index_to_play_name.items()}

        self.get_blocks()
        if len(self.blocks) != len(self.index_to_formation_name):
            raise ValueError(f"Block count ({len(self.blocks)}) does not match formation name count ({len(self.index_to_formation_name)})")

        # --- 3. Build Formation Objects ---
        self.playbook_formations = {}

        for i, (block_start, rows) in enumerate(self.blocks):
            formation_name = self.index_to_formation_name[i]
            
            # Last row is the package row
            package_row = rows[-1]
            package_idx = package_row[0]
            package_name = self.index_to_package_name.get(package_idx, f"Unknown({package_idx})")

            formation = formations[formation_name]
            formation.package = package_name
            formation.starting_address = block_start

            # Play rows are all rows except the last
            for row in rows[:-1]:
                if row[0] == PB_PSU.FF_SENTINEL[0] and row[1] == PB_PSU.FF_SENTINEL[1]:
                    break
                formation.play_bytes.append((row[0], row[1]))
                play_index = row[0] + (256 if row[1] == 0x01 else 0)
                formation.plays.append(self.index_to_play_name.get(play_index))

            self.playbook_formations[formation_name] = formation

        # Build master play list from all formations at load time
        self.all_playbook_plays = set()
        for formation in self.playbook_formations.values():
            if formation.side.lower() not in ("offense", "offensive"):
                continue
            for pb in formation.play_bytes:
                self.all_playbook_plays.add(pb)

def load_csv_data():
    formations = {}
    package_names = set()
    play_names = set()

    with open('nfl2k5_playbook.csv', 'r') as csv_file:
        reader = csv.reader(csv_file, delimiter=",")
        for row in reader:
            team = row[0]
            # Skip header row
            if team == "Team": 
                continue
            side = row[1]
            formation = row[2]
            package = row[3]
            play = row[4]
            if formation not in formations:
                formations[formation] = Formation(formation, side)
            package_names.add(package)
            play_names.add(play)
    return formations, package_names, play_names

def main():
    psu = PB_PSU('a1.psu')
    formations, package_names, play_names = load_csv_data()
    psu.load_playbook(formations, package_names, play_names)

if __name__=="__main__":
    main()