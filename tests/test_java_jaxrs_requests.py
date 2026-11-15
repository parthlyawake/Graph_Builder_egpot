"""JAX-RS typed builder propagation does not guess arbitrary Java clients."""
from graft_ckg import CKGBuilder
from java_jaxrs_requests import extract_jaxrs_requests


def test_jaxrs_environment_default_and_bounded_string_format(tmp_path):
    source = """
import javax.ws.rs.client.Client;
import javax.ws.rs.client.ClientBuilder;
import javax.ws.rs.client.WebTarget;
import javax.ws.rs.client.Invocation;
class Backend {
    static String hostname = System.getenv("HOSTNAME") == null
          ? "ratings" : System.getenv("HOSTNAME");
    static String endpoint = String.format("http://%s:9080/ratings", hostname);
    void use(String id) {
        Client client = ClientBuilder.newBuilder().build();
        WebTarget target = client.target(endpoint + "/" + id);
        Invocation.Builder request = target.request();
        request.get();
    }
}
"""
    (tmp_path / "Backend.java").write_text(source)
    builder = CKGBuilder(str(tmp_path))
    builder.build()
    result = extract_jaxrs_requests(builder, "Backend.java", source, {})
    assert len(result) == 1
    assert result[0][1] == "http://ratings:9080/ratings/*"
    assert result[0][-1] == "java_jaxrs_conditional_default"
    set_env = extract_jaxrs_requests(builder, "Backend.java", source,
                                     {"HOSTNAME": "ratings-v2"})
    assert len(set_env) == 1
    assert set_env[0][1] == "http://ratings-v2:9080/ratings/*"
    assert set_env[0][-1] == "java_jaxrs_typed_client"
