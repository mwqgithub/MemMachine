import logging
import os
import platform
import shutil
import subprocess
import urllib.request
import zipfile
from abc import ABC, abstractmethod
from typing import Dict, Optional
import importlib.resources

import psutil
from configuration_wizard import ConfigurationWizard, ConfigurationWizardArgs

WINDOWS_DEFAULT_NEO4J_INSTALL_DIR = "C:\\Program Files\\Neo4j"
JDK_URL = "https://download.oracle.com/java/21/latest/jdk-21_windows-x64_bin.zip"
NEO4J_URL = "https://dist.neo4j.org/neo4j-community-2025.09.0-windows.zip"
JDK_ZIP_NAME = "jdk-21_windows-x64_bin.zip"
NEO4J_ZIP_NAME = "neo4j-community-2025.09.0-windows.zip"
NEO4J_WINDOWS_SERVICE_NAME = "neo4j"

JDK_DIR_NAME = "jdk-21.0.9"
NEO4J_DIR_NAME = "neo4j-community-2025.09.0"


class Installer(ABC):
    def __init__(self, logger: logging.Logger):
        self.logger = logger

        # Maybe we can let the user decide these values later
        self.neo4j_host = "localhost"
        self.neo4j_port = 7687
        self.neo4j_user = "neo4j"
        self.neo4j_password = "neo4j"

    @abstractmethod
    def install_and_start_neo4j(self):
        pass

    @abstractmethod
    def check_neo4j_running(self) -> bool:
        pass

    @abstractmethod
    def get_run_script_type(self) -> str:
        pass

    def install(self):
        if not self.check_neo4j_running():
            choice = (
                input(
                    "Neo4j is not running. Do you want to install and start Neo4j? (y/n): "
                )
                .strip()
                .lower()
            )
            if choice != "y":
                raise Exception(
                    "Neo4j installation is required to proceed. Exiting installation."
                )
            self.install_and_start_neo4j()
            neo4j_started_by_installer = True
        else:
            self.logger.info("Neo4j is already running.")

        wizard_args = ConfigurationWizardArgs(
            neo4j_provided=neo4j_started_by_installer,
            neo4j_host=self.neo4j_host,
            neo4j_port=self.neo4j_port,
            neo4j_user=self.neo4j_user,
            neo4j_password=self.neo4j_password,
            config_sources={
                "CPU": importlib.resources.files("memmachine").joinpath(
                    "sample_configs/episodic_memory_config.cpu.sample"
                ),
                "GPU": importlib.resources.files("memmachine").joinpath(
                    "sample_configs/episodic_memory_config.gpu.sample"
                ),
            },
            destination=os.path.expanduser("~/.config/.memmachine/"),
            run_script_type=self.get_run_script_type(),
        )
        wizard = ConfigurationWizard(
            wizard_args,
            logger=self.logger,
        )
        wizard.run_wizard()

        self.logger.info("MemMachine installation and configuration completed.")
        self.logger.info(
            "Please run memmachine-nltk-setup and memmachine-sync-profile-schema to complete the setup."
        )

class LinuxEnvironment:
    def __init__(self, logger: logging.Logger):
        super().__init__(logger)

    def install_and_start_neo4j(self):
        pass

    def neo4j_installed(self) -> bool:
        pass

class LinuxInstaller(Installer):
    def __init__(self, logger: logging.Logger, environment: Optional[LinuxEnvironment] = None):
        super().__init__(logger)
        if environment is None:
            self.environment = LinuxEnvironment(logger)
        else:
            self.environment = environment

    def get_run_script_type(self):
        return "bash"

    def check_neo4j_running(self) -> bool:
        return self.environment.neo4j_installed()

    def install_and_start_neo4j(self):
        self.environment.install_and_start_neo4j()

class MacosEnvironment:
    def __init__(self, logger: logging.Logger):
        super().__init__(logger)

    def install_and_start_neo4j(self):
        subprocess.run(["brew", "install", "neo4j"], check=True)
        subprocess.run(["brew", "services", "start", "neo4j"], check=True)

    def neo4j_installed(self) -> bool:
        result = subprocess.run(
            ["brew", "list", "--versions", "neo4j"], capture_output=True, text=True
        )
        return result.returncode == 0 and result.stdout.strip() != ""


class MacosInstaller(Installer):
    def __init__(self, logger: logging.Logger, environment: Optional[MacosEnvironment] = None):
        super().__init__(logger)
        if environment is None:
            self.environment = MacosEnvironment(logger)
        else:
            self.environment = environment

    def get_run_script_type(self):
        return "bash"

    def check_neo4j_running(self) -> bool:
        return self.environment.neo4j_installed()

    def install_and_start_neo4j(self):
        self.environment.install_and_start_neo4j()


class WindowsEnvironment:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def download_file(self, url: str, dest: str):
        urllib.request.urlretrieve(url, dest)

    def extract_zip(self, zip_path: str, extract_to: str):
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_to)

    def start_neo4j_service(self, install_dir: str):
        subprocess.run(
            [
                "powershell.exe",
                "-File",
                os.path.join(install_dir, NEO4J_DIR_NAME, "bin", "neo4j.ps1"),
                "windows-service",
                "install",
            ],
            env={**os.environ.copy(), **self.get_neo4j_env(install_dir=install_dir)},
            check=True,
        )
        subprocess.run(
            [
                "powershell.exe",
                "-File",
                os.path.join(install_dir, NEO4J_DIR_NAME, "bin", "neo4j.ps1"),
                "windows-service",
                "start",
            ],
            env={**os.environ.copy(), **self.get_neo4j_env(install_dir=install_dir)},
            check=True,
        )

    def get_neo4j_env(self, install_dir: str) -> Dict[str, str]:
        return {
            "JAVA_HOME": os.path.join(install_dir, JDK_DIR_NAME),
            "NEO4J_HOME": os.path.join(install_dir, NEO4J_DIR_NAME),
        }

    def check_neo4j_running(self) -> bool:
        try:
            service = psutil.win_service_get(NEO4J_WINDOWS_SERVICE_NAME)
            service_info = service.as_dict()
            if service_info["status"] != "running":
                self.logger.warning(
                    "Neo4j service is installed but not running. Please start the service before running MemMachine."
                )
            return True
        except Exception:
            return False


class WindowsInstaller(Installer):
    def __init__(
        self, logger: logging.Logger, environment: Optional[WindowsEnvironment] = None
    ):
        super().__init__(logger)
        self.install_dir = WINDOWS_DEFAULT_NEO4J_INSTALL_DIR
        if environment is None:
            self.environment = WindowsEnvironment(logger)
        else:
            self.environment = environment

    def get_run_script_type(self):
        return "powershell"

    def check_neo4j_running(self) -> bool:
        return self.environment.check_neo4j_running()

    def ask_install_dir(self):
        install_dir = input(
            f"Enter Neo4j installation directory [{self.install_dir}]: "
        ).strip()
        if install_dir:
            self.install_dir = install_dir

    def install_and_start_neo4j(self):
        self.logger.info("Installing Neo4j Community Edition...")
        self.ask_install_dir()
        self.logger.info("Downloading and installing OpenJDK 21...")
        jdk_zip_path = os.path.join(self.install_dir, JDK_ZIP_NAME)
        self.environment.download_file(JDK_URL, jdk_zip_path)
        self.environment.extract_zip(jdk_zip_path, self.install_dir)
        self.logger.info("OpenJDK 21 installed successfully.")
        self.logger.info(
            "Downloading and installing Neo4j Community Edition 2025.09.0..."
        )
        neo4j_zip_path = os.path.join(self.install_dir, NEO4J_ZIP_NAME)
        self.environment.download_file(NEO4J_URL, neo4j_zip_path)
        self.environment.extract_zip(neo4j_zip_path, self.install_dir)
        self.logger.info("Neo4j Community Edition installed successfully.")
        # delete zip files
        os.remove(jdk_zip_path)
        os.remove(neo4j_zip_path)
        # install and start neo4j service
        self.logger.info("Starting Neo4j service...")
        self.environment.start_neo4j_service(self.install_dir)
        self.logger.info("Neo4j service started.")


def main():
    logger = logging.getLogger("MemMachineInstaller")
    try:
        system = platform.system()
        if system == "Windows":
            WindowsInstaller(logger).install()
        elif system == "Darwin":
            MacosInstaller(logger).install()
        else:
            raise Exception(f"Unsupported operating system: {system}")
    except Exception as e:
        logger.error(f"Installation failed: {e}")


if __name__ == "__main__":
    main()
