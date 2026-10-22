"""Publish task: put a finished volume on the site. Guarded: it runs only with `--yes`, and it is never pulled in as somebody else's prerequisite.

It prepares the package (pdf, cover, cast pictures, metadata with the making-of numbers), copies it to the production host and runs the remote publisher
there. The host comes from `--prod user@host` or SUTUR_PROD_HOST. Needs an ssh agent that holds the production key (`ssh -A` from your machine); no key is
stored on the GPU server. Review the sheets first."""

from __future__ import annotations

import os

from ..errors import ConfigError
from ..publishing import SshTransport, Transport, build_package, upload
from .base import Context, Kind, Result, Task
from .registry import register

HOST_ENV = "SUTUR_PROD_HOST"   # user@host of the production server; never written into the code


@register
class PublishTask(Task):
    name = "publish"
    kind = Kind.TRANSFORM
    requires = ("pdf",)
    guarded = True
    description = "Publish the volume to the site (needs --yes, a host and the production key in your ssh agent)."

    def preflight(self, ctx: Context) -> list[str]:
        problems = []
        if "yes" not in ctx.options and not ctx.dry_run:
            problems.append("publish puts the volume on the site: review the sheets first, then run with --yes")
        for needed in ("publish.json", "cast.json", "cover-final.png", f"vol{ctx.workspace.ref.volume}.pdf"):
            if not (ctx.workspace.dir / needed).exists():
                problems.append(f"{needed} is missing")
        return problems

    def run(self, ctx: Context) -> Result:
        host = ctx.options.get("prod") or os.environ.get(HOST_ENV, "")
        if not host:
            raise ConfigError(f"set the production host: --prod user@host or {HOST_ENV}")
        if ctx.dry_run:
            return Result.success(f"would publish {ctx.workspace.ref} to {host}")
        package = build_package(ctx.workspace)
        transport: Transport = ctx.transport or SshTransport(host)
        upload(package, transport, host)
        return Result.success(f"published {package.slug} to {host}", slug=package.slug)
