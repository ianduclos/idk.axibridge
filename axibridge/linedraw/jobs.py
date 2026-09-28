"""Bounded, cancellable draft jobs. This module never mutates a project."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import threading
import time
import uuid
from ..assets import asset_store
from ..render_work import RenderCancelled
from ..model import PathDocument
from .contracts import LinedrawV3Params
from . import runtime
from .engine import render_document


@dataclass
class Job:
    id: str
    revision: str
    params: LinedrawV3Params
    operation: str
    image: bytes
    project: object | None = None
    state: str = "queued"
    progress: float = 0
    message: str = ""
    result: dict | None = None
    document: PathDocument | None = None
    error: str | None = None
    created: float = field(default_factory=time.monotonic)
    cancel: threading.Event = field(default_factory=threading.Event)


class JobManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = {}
        self.executor = None

    def start(self, revision, params, operation, project=None):
        params = LinedrawV3Params(**params) if isinstance(params, dict) else params
        if operation not in ("analyze", "render"):
            raise ValueError("Unknown drawing operation")
        name = asset_store.resolve_frame(params.image, params.frame)
        data = asset_store.get(name)
        if not data:
            raise ValueError("Select an uploaded image first")
        with self.lock:
            terminal = [
                j
                for j in self.jobs.values()
                if j.state in ("complete", "cancelled", "failed")
            ]
            for i, j in enumerate(
                sorted(terminal, key=lambda j: j.created, reverse=True)
            ):
                if i >= 16 or time.monotonic() - j.created > 1800:
                    self.jobs.pop(j.id, None)
            if sum(j.state in ("queued", "running") for j in self.jobs.values()) >= 3:
                raise ValueError("Drawing queue is full; cancel a pending analysis")
            job = Job(uuid.uuid4().hex, revision, params, operation, data, project)
            self.jobs[job.id] = job
            if self.executor is None:
                self.executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="linedraw"
                )
            self.executor.submit(self._run, job)
            return self.get(job.id)

    def get(self, identity):
        with self.lock:
            j = self.jobs[identity]
            return dict(
                id=j.id,
                revision=j.revision,
                state=j.state,
                progress=j.progress,
                message=j.message,
                result=j.result,
                error=j.error,
            )

    def cancel(self, identity):
        with self.lock:
            j = self.jobs[identity]
            if j.state in ("queued", "running"):
                j.cancel.set()
                j.state = "cancelled"
                j.result = None
            return self.get(identity)

    def completed_snapshot(self, identity, revision, project):
        """Return only the completed geometry bound to this live project.

        Keep the project reference, rather than its name or path: New and Load
        replace the object even when the next project has the same name.
        """
        with self.lock:
            job = self.jobs[identity]
            if job.revision != revision:
                raise ValueError("Drawing revision is stale")
            if job.project is not project:
                raise ValueError("Drawing belongs to a different project")
            if job.state != "complete" or job.document is None:
                raise ValueError("Drawing is not complete")
            return job.document, job.params

    def _run(self, j):
        def check():
            if j.cancel.is_set():
                raise RenderCancelled()

        def progress(frac, message):
            check()
            with self.lock:
                j.progress = frac
                j.message = message

        try:
            check()
            with self.lock:
                j.state = "running"
            p = j.params
            if j.operation == "analyze":
                p = p.model_copy(update={"image_identity": "", "faces": [],
                    "people": [person.model_copy(update={"face_id": ""}) for person in p.people]})
            evidence = runtime.detect_and_analyze(
                j.image,
                p,
                cancel=j.cancel,
                progress=progress,
                detect=j.operation == "analyze",
            )
            p = p.model_copy(
                update={
                    "faces": list(evidence.faces),
                    "image_identity": runtime.image_identity(j.image),
                    "model_identity": runtime.model_identity(),
                }
            )
            progress(0.95, "Building pen paths")
            doc = render_document(evidence, p, checkpoint=check)
            check()
            warnings = []
            if not p.faces and p.style != "light_support":
                warnings.append("No face regions. Add a region to request face detail.")
            if not (evidence.foreground > 0.35).any():
                warnings.append("No person foreground found; the drawing is empty.")
            if p.style == "regional_form" and not p.detail_regions:
                warnings.append("Base form only. Add detail regions to recover hands, clothing or hair.")
            if j.operation == "analyze" and p.people:
                warnings.append("Faces redetected; check each person's face link.")
            result = dict(
                params=p.model_dump(),
                faces=[f.model_dump() for f in p.faces],
                image_identity=p.image_identity,
                evidence_identity=evidence.identity,
                warnings=warnings,
                diagnostics={"device": evidence.device},
                preview=dict(
                    lines=[path.points for _, path in doc.iter_paths()],
                    components=[dict(
                        id=layer.name,
                        label={"contours": "Contours", "form": "Form", "cores": "Cores"}[layer.name],
                        lines=[path.points for path in layer.paths],
                        count=len(layer.paths),
                    ) for layer in doc.layers],
                    width=doc.width,
                    height=doc.height,
                ),
            )
            with self.lock:
                check()
                j.params = p
                j.document = doc
                j.result = result
                j.state = "complete"
                j.progress = 1
                j.message = "Drawing ready"
        except RenderCancelled:
            with self.lock:
                j.state = "cancelled"
                j.result = None
        except Exception as exc:
            with self.lock:
                if not j.cancel.is_set():
                    j.state = "failed"
                    j.error = str(exc)
        finally:
            j.image = b""  # Finished jobs need no duplicate of source bytes.

    def shutdown(self):
        with self.lock:
            for j in self.jobs.values():
                if j.state in ("queued", "running"):
                    j.cancel.set()
                    j.state = "cancelled"
            executor = self.executor
            self.executor = None
        if executor:
            executor.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            self.jobs.clear()


manager = JobManager()
