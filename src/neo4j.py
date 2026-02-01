import os
import time
import subprocess
from pathlib import Path

def find_dump_path(dataset_folder_path):
    # Convert string path to a Path object
    base_path = Path(dataset_folder_path)
    
    # Use glob to find files matching the pattern "*.dump"
    # This returns a generator of all matching paths
    dump_files = list(base_path.glob("*.dump"))
    
    if not dump_files:
        raise FileNotFoundError(f"No .dump file found in {dataset_folder_path}")
    
    # If there are multiple, you might want the latest version or just the first one
    # Sorting ensures consistent results if multiple versions exist
    dump_files.sort()
    
    # Return the absolute path as a string
    return str(dump_files[-1].absolute())


class Neo4jManager:
    def __init__(self, neo4j_home, dataset_home):
        self.neo4j_home = Path(neo4j_home).absolute()
        self.dataset_home = Path(dataset_home).absolute()
        self.bin = os.path.join(self.neo4j_home, "bin", "neo4j")
        self.admin = os.path.join(self.neo4j_home, "bin", "neo4j-admin")

    def load(self, dataset):
        self.stop()

        print(f"📦 Loading Neo4j dataset {dataset}...")
        dataset_dir = f"{self.dataset_home}/{dataset}"
        dump_file_path = find_dump_path(dataset_dir)

        load_command = [
            self.admin, 
            "load", 
            f"--from={dump_file_path}", 
            "--database=neo4j", 
            "--force"
        ]

        print(load_command)
        subprocess.run(load_command, check=True)

    def start(self):
        print("🚀 Starting Neo4j...")
        subprocess.run([self.bin, "start"], check=True)
        # Give it a few seconds to warm up the JVM
        time.sleep(5)

    def stop(self):
        print("🛑 Stopping Neo4j...")
        subprocess.run([self.bin, "stop"], check=True)

def main():
    manager = Neo4jManager(neo4j_home="../neo4j-community-4.4.46", dataset_home="./data/datasets/")
    manager.load("star-wars")
    manager.start()

if __name__ == "__main__":
    main()