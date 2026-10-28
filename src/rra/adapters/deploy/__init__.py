"""배포 정보 어댑터 — `data/deploy/version.json`(tools/deploy.sh 가 씀) 읽기, 없으면 git 에서."""

from rra.adapters.deploy.version import read_version

__all__ = ["read_version"]
