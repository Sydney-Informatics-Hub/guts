__author__ = "Fred Jaya, Vanessa Sochat"
__copyright__ = "Copyright 2022-2024, Vanessa Sochat"
__license__ = "MPL 2.0"


import json
import os

import container_guts.utils as utils

from .base import ContainerName, ContainerTechnology
from .decorator import ensure_container


class SingularityContainerName(ContainerName):
    def parse(self, raw):
        if os.path.isabs(raw):
            """
            CVMFS image uses the raw value as the path, and parse the tool/tag from the basename.
            """
            basename = os.path.basename(raw)
            self.tool, _, self.tag = basename.partition(":")
            if not self.tag:
                self.tag = "latest"
            self.registry = None
            self.namespace = None
            self.digest = None
            self.version = None
        else:
            super().parse(raw)

    @property
    def uri(self):
        if os.path.isabs(self.raw):
            return self.raw
        return f"docker://{super().uri}"


class SingularityContainer(ContainerTechnology):
    """
    A Singularity container controller.
    """

    command = "singularity"

    def get_container(self, image):
        """
        Courtesy function to get a container from a URI.
        """
        if isinstance(image, SingularityContainerName):
            return image
        if isinstance(image, ContainerName):
            return SingularityContainerName(image.raw)
        return SingularityContainerName(image)

    @ensure_container
    def shell(self, image):
        """
        Interactive shell into a container image.
        """
        os.system(f"{self.command} shell {image.uri}")

    @ensure_container
    def cleanup(self, image):
        """
        Nothing to clean up: CVMFS images are read-only, pulled SIF files
        are left in place for reuse.
        """
        pass

    @ensure_container
    def export(self, image, tmpdir=None, cleanup=True):
        """
        Export a Singularity image into a directory.

        Uses 'singularity build --sandbox' to extract the full filesystem
        into root/, and 'singularity inspect --json' to write meta/config.json
        in the format get_manifests() expects.
        """
        if not tmpdir:
            tmpdir = utils.get_tmpdir()

        export_dir = os.path.join(tmpdir, "root")
        meta_dir = os.path.join(tmpdir, "meta")
        os.makedirs(export_dir)
        os.makedirs(meta_dir)

        self.pull(image)
        self.call([self.command, "build", "--sandbox", export_dir, image.uri])

        labels = {}
        res = self.call(
            [self.command, "inspect", "--json", image.uri],
            stream=False,
            allow_fail=True,
        )
        if res["return_code"] == 0:
            try:
                labels = (
                    json.loads(res["message"])
                    .get("data", {})
                    .get("attributes", {})
                    .get("labels", {})
                )
            except Exception:
                pass

        config = {
            "config": {
                "Env": [],
                "Labels": labels,
                "Entrypoint": None,
                "Cmd": None,
                "WorkingDir": None,
            }
        }
        utils.write_json(config, os.path.join(meta_dir, "config.json"))
        return tmpdir

    @ensure_container
    def execute(self, image, command):
        """
        Execute a command in a container image.
        """
        cmd = [self.command, "exec", image.uri] + command
        return self.call(cmd, stream=False)

    @ensure_container
    def run(self, image, command, entrypoint=None, **_):
        """
        Run a command in a container. Singularity has no detached/daemon mode
        or named containers, so those parameters are ignored.
        """
        if entrypoint:
            cmd = [self.command, "exec", image.uri, entrypoint] + command
        else:
            cmd = [self.command, "run", image.uri] + command
        print(" ".join(cmd))
        return self.call(cmd)

    @ensure_container
    def pull(self, image):
        """
        Pull a container image. Skipped if the image already exists on disk.
        """
        if os.path.exists(image.raw):
            return
        return self.call([self.command, "pull", image.uri])

    @ensure_container
    def inspect(self, image):
        """
        Inspect an image.
        """
        res = self.call([self.command, "inspect", "--json", image.uri], stream=False)
        return json.loads(res["message"])
