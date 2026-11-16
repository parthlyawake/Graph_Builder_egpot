"""Real pinned Online Boutique EmailService RPC -> OTLP on a CI runner.

Runs the ORIGINAL benchmark Python dummy service, not a replacement handler.
Receives actual gRPC server spans in a local OTLP collector. The build/deploy
join and resource identity are self-reported CI metadata, NOT externally
authenticated; a verified DSSE/SLSA attestation and real rollout are absent.
"""
from __future__ import annotations
import argparse
from concurrent import futures
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

import grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc

PIN="38e7348eb289eb5b87c0c6e8cb19ced0449dc389"

class Collector(trace_service_pb2_grpc.TraceServiceServicer):
    def __init__(self):
        self.lock=threading.Lock()
        self.records=[]
    def Export(self,request,context):
        with self.lock:
            for resources in request.resource_spans:
                attrs={v.key:(v.value.string_value or str(v.value.int_value))
                       for v in resources.resource.attributes}
                for scope in resources.scope_spans:
                    for sp in scope.spans:
                        self.records.append({
                            "resource":attrs,
                            "name":sp.name,
                            "trace_id":sp.trace_id.hex(),
                            "span_id":sp.span_id.hex(),
                            "start_time_unix_nano":sp.start_time_unix_nano,
                            "end_time_unix_nano":sp.end_time_unix_nano
                        })
        return trace_service_pb2.ExportTraceServiceResponse()

def reserve_port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]

def run(repo:Path)->dict:
    # Resolve before using app.parent as the child process cwd.
    repo=repo.resolve()
    got=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    if got!=PIN:
        raise ValueError("Source revision changed: "+got)
    app=repo/"src/emailservice/email_server.py"
    if not app.is_file():
        raise ValueError("Actual benchmark email_server.py missing")
    with tempfile.TemporaryDirectory(prefix="p3-email-") as tmp:
        generated=Path(tmp)/"generated"
        generated.mkdir()
        subprocess.run([sys.executable,"-m","grpc_tools.protoc",
                        "-I",str(repo/"protos"),"--python_out="+str(generated),
                        "--grpc_python_out="+str(generated),
                        str(repo/"protos/demo.proto")],check=True)
        # Local CI collector uses a genuine OTLP TraceService Export endpoint.
        collector=Collector()
        sink=grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(collector,sink)
        otlp_port=sink.add_insecure_port("127.0.0.1:0")
        sink.start()
        port=reserve_port()
        env=os.environ.copy()
        env.update({
            "ENABLE_TRACING":"1","DISABLE_PROFILER":"1",
            "COLLECTOR_SERVICE_ADDR":f"127.0.0.1:{otlp_port}",
            "PORT":str(port),
            "OTEL_SERVICE_NAME":"emailservice-ci-research",
            "OTEL_RESOURCE_ATTRIBUTES":f"service.version={PIN},deployment.environment.name=ephemeral-ci,source.git.commit={PIN}",
            "OTEL_BSP_SCHEDULE_DELAY":"500",
            "PYTHONPATH":os.pathsep.join([str(generated),str(app.parent),env.get("PYTHONPATH","")])
        })
        proc=subprocess.Popen([sys.executable,str(app)],cwd=app.parent,
                              env=env,stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,text=True)
        grpc_error=None
        responses=0
        logs=""
        try:
            import importlib
            sys.path.insert(0,str(generated))
            pb=importlib.import_module("demo_pb2")
            pbgrpc=importlib.import_module("demo_pb2_grpc")
            channel=grpc.insecure_channel(f"127.0.0.1:{port}")
            grpc.channel_ready_future(channel).result(timeout=18)
            stub=pbgrpc.EmailServiceStub(channel)
            for i in range(5):
                response=stub.SendOrderConfirmation(
                    pb.SendOrderConfirmationRequest(email=f"ci-verified-{i}@example.invalid"),
                    timeout=5)
                if isinstance(response,pb.Empty):
                    responses+=1
            for _ in range(60):
                with collector.lock:
                    matching=[r for r in collector.records if "SendOrderConfirmation" in r["name"]]
                if len(matching)>=responses:
                    break
                time.sleep(.25)
            channel.close()
        except Exception as exc:
            grpc_error=repr(exc)
        finally:
            proc.send_signal(signal.SIGINT)
            try:
                logs,_=proc.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                proc.kill()
                logs,_=proc.communicate(timeout=5)
            sink.stop(grace=1)
        with collector.lock:
            records=list(collector.records)
        server_rpc=[r for r in records if "SendOrderConfirmation" in r["name"]]
        has_resource=any(r["resource"].get("service.version")==PIN for r in server_rpc)
        result={
            "source_repository":"GoogleCloudPlatform/microservices-demo",
            "source_sha":PIN,
            "source_sha256":hashlib.sha256(app.read_bytes()).hexdigest(),
            "deployment_type":"real benchmark EmailService dummy implementation launched as ephemeral CI process",
            "pid":proc.pid,"exit_code":proc.returncode,
            "collected_otlp_export_batches_nonzero":bool(records),
            "successful_rpc_responses":responses,
            "captured_otlp_server_spans":len(server_rpc),
            "resource_contains_expected_reported_source_sha":has_resource,
            "resource_identity_assurance":"self-reported environment attributes; NOT verified attestation",
            "attestation_verified":False,
            "runtime_artifact_deployment_provenance_authenticated":False,
            "error":grpc_error,
            "spans":server_rpc[:30],
            "stdout_tail":logs[-6000:]
        }
        result["functional_pass"]=bool(responses==5 and len(server_rpc)>=5 and has_resource and not grpc_error)
        return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        result=run(args.repo)
    except Exception as exc:
        result={"functional_pass":False,"error":repr(exc),
                "authenticity":"UNVERIFIED","source_revision":PIN}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("REAL_BENCHMARK_RPC_OTLP",json.dumps({
        k:result.get(k) for k in ("functional_pass","successful_rpc_responses",
                                  "captured_otlp_server_spans",
                                  "resource_contains_expected_reported_source_sha",
                                  "attestation_verified","error")},sort_keys=True),flush=True)
    return 0 if result.get("functional_pass") else 2

if __name__=="__main__":
    raise SystemExit(main())
