"""
Unit tests verifying fixes for:
1. Incremental Protobuf updates during streaming build (update_files)
2. Traversal choke-point bypass on service contract nodes
"""

import os
import tempfile
import unittest

from graft_ckg import CKGBuilder
from traversal import SCKGTraversal


class ProtoChokePointFixesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_incremental_protobuf_update_refreshes_contracts(self):
        """Verify that updating a .proto file properly updates contract nodes and removes obsolete ones."""
        proto_v1 = """syntax = "proto3";
package demo;

service UserService {
    rpc GetUser (UserRequest) returns (UserResponse);
}
"""
        proto_path = os.path.join(self.repo_dir, "user.proto")
        with open(proto_path, "w", encoding="utf-8") as f:
            f.write(proto_v1)

        builder = CKGBuilder(self.repo_dir)
        builder.build()

        self.assertTrue(builder.graph.has_node("contract::UserService"))
        self.assertTrue(builder.graph.has_node("contract::UserService.GetUser"))
        self.assertFalse(builder.graph.has_node("contract::UserService.DeleteUser"))

        # Now update user.proto: replace GetUser with DeleteUser
        proto_v2 = """syntax = "proto3";
package demo;

service UserService {
    rpc DeleteUser (DeleteRequest) returns (DeleteResponse);
}
"""
        with open(proto_path, "w", encoding="utf-8") as f:
            f.write(proto_v2)

        # Incrementally update
        builder.update_files(["user.proto"])

        # DeleteUser should now exist
        self.assertTrue(builder.graph.has_node("contract::UserService.DeleteUser"))
        # GetUser should have been pruned cleanly
        self.assertFalse(builder.graph.has_node("contract::UserService.GetUser"))
        # Service contract should remain fresh
        self.assertTrue(builder.graph.has_node("contract::UserService"))
        self.assertIn("DeleteUser", builder.proto_services["UserService"]["rpcs"])
        self.assertNotIn("GetUser", builder.proto_services["UserService"]["rpcs"])

    def test_traversal_bypasses_service_choke_point(self):
        """Verify that traversing from an RPC consumer does not explode into sibling RPCs of that service."""
        proto_content = """syntax = "proto3";
package demo;

service BillingService {
    rpc ProcessInvoice (InvoiceReq) returns (InvoiceResp);
    rpc ProcessRefund (RefundReq) returns (RefundResp);
    rpc CancelSubscription (CancelReq) returns (CancelResp);
}
"""
        proto_path = os.path.join(self.repo_dir, "billing.proto")
        with open(proto_path, "w", encoding="utf-8") as f:
            f.write(proto_content)

        # Consumer code that only calls ProcessInvoice
        consumer_py = """
def trigger_billing(client, req):
    return client.ProcessInvoice(req)
"""
        py_path = os.path.join(self.repo_dir, "caller.py")
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(consumer_py)

        builder = CKGBuilder(self.repo_dir)
        builder.build()

        # Manually link caller to contract::BillingService.ProcessInvoice via CONSUMES
        caller_node = "caller.py:trigger_billing"
        rpc_target = "contract::BillingService.ProcessInvoice"
        builder.graph.add_edge(caller_node, rpc_target, relation="CONSUMES", layer="Lcontract")

        traversal = SCKGTraversal(builder)
        graft = traversal.deterministic_subtree_graft(caller_node, max_tokens=2048)

        selected = set(graft["selected_nodes"])
        self.assertIn(caller_node, selected)
        self.assertIn(rpc_target, selected)

        # Sibling RPCs must NOT be pulled in through the choke point!
        self.assertNotIn("contract::BillingService.ProcessRefund", selected)
        self.assertNotIn("contract::BillingService.CancelSubscription", selected)


if __name__ == "__main__":
    unittest.main()
