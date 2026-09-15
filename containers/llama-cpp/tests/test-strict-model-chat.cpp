#include "common.h"
#include "json.h"
#include "server-chat-model.h"

#include <cpp-httplib/httplib.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

using json = common_json;

// These checks intentionally remain active in Release builds with NDEBUG.
#define CHECK(condition) do { if (!(condition)) { \
    throw std::runtime_error(std::string(__FILE__) + ":" + std::to_string(__LINE__) + ": " #condition); \
} } while (false)

static const std::vector<std::string> paths = {"/chat/completions", "/v1/chat/completions"};
static const std::string canonical = "glm-5.3";
// Secondary names are test declarations, not proposed production aliases.
static const json model_info = json::object({
    {"id", canonical}, {"aliases", json::array({"native-secondary", "declared-secondary"})},
});
static const std::string conversation = "d3p-existing-conversation";
static const std::string test_credential = "d3p-public-test-fixture";

struct counters {
    int generator = 0;
    int wake = 0;
    int chat_template = 0;
    int session = 0;
    int queue = 0;
    int next = 0;
    int complete = 0;

    bool operator==(const counters & other) const {
        return generator == other.generator && wake == other.wake && chat_template == other.chat_template &&
               session == other.session && queue == other.queue && next == other.next && complete == other.complete;
    }
};

struct fake_downstream {
    mutable std::mutex mutex;
    std::condition_variable completed;
    counters calls;
    std::string existing_session = "original-session";
    std::string last_body;
    std::string last_path;
    std::string last_query;
    std::map<std::string, std::string> last_headers;
    std::map<std::string, std::string> last_params;
    const server_http_req * last_request = nullptr;
    server_http_res * last_response = nullptr;

    struct response : server_http_res {
        fake_downstream & owner;
        explicit response(fake_downstream & owner) : owner(owner) {}
        void on_complete() override {
            std::lock_guard<std::mutex> lock(owner.mutex);
            ++owner.calls.complete;
            owner.completed.notify_all();
        }
    };

    counters snapshot() const {
        std::lock_guard<std::mutex> lock(mutex);
        return calls;
    }

    std::string session_snapshot() const {
        std::lock_guard<std::mutex> lock(mutex);
        return existing_session;
    }

    void wait_for_complete(int expected) {
        std::unique_lock<std::mutex> lock(mutex);
        CHECK(completed.wait_for(lock, std::chrono::seconds(5), [&] { return calls.complete == expected; }));
    }

    server_http_res_ptr operator()(const server_http_req & req) {
        std::lock_guard<std::mutex> lock(mutex);
        ++calls.generator;
        ++calls.wake;
        ++calls.chat_template;
        ++calls.session;
        ++calls.queue;
        if (req.headers.count("X-Conversation-Id")) {
            existing_session = "replaced-session-" + std::to_string(calls.session);
        }
        last_request = &req;
        last_body = req.body;
        last_path = req.path;
        last_query = req.query_string;
        last_headers = req.headers;
        last_params = req.params;
        auto res = std::make_unique<response>(*this);
        res->headers["X-D3P-Delegated"] = "yes";
        const auto body = json::parse_no_throw(req.body);
        if (body.is_object() && body.contains("stream") && body.at("stream") == true) {
            res->content_type = "text/event-stream";
            res->next = [this](std::string & chunk) {
                std::lock_guard<std::mutex> next_lock(mutex);
                ++calls.next;
                chunk = "data: {\"model\":\"glm-5.3\",\"choices\":[]}\n\ndata: [DONE]\n\n";
                return false;
            };
        } else {
            res->data = json::object({{"model", canonical}, {"fixture", "delegated"}}).dump();
        }
        last_response = res.get();
        return res;
    }
};

struct fixture {
    common_params params;
    fake_downstream downstream;
    std::atomic<int> metadata_reads{0};
    server_http_context http;

    fixture(bool router = false, bool child = false, bool listen = false) {
        params.hostname = "127.0.0.1";
        params.port = 0;
        params.n_threads_http = 1;
        params.ui = false;
        params.api_keys = {test_credential};
        CHECK(http.init(params));
        auto handler = server_chat_model_guard(
            [this](const server_http_req & req) { return downstream(req); }, router, child,
            [this]() { ++metadata_reads; return model_info; });
        server_chat_register_routes(http, handler);
        CHECK(http.handlers.size() == 2);
        for (const auto & path : paths) {
            CHECK(http.handlers.count(path) == 1);
        }
        if (listen) {
            CHECK(http.start());
            CHECK(http.hostname == "127.0.0.1");
            CHECK(http.port > 0);
        }
    }

    ~fixture() {
        http.stop();
        if (http.thread.joinable()) {
            http.thread.join();
        }
    }
};

enum class outcome { delegate, unknown, malformed_model, malformed_body };
struct input_case {
    std::string label;
    std::string body;
    outcome expected;
    bool stream;
};

static std::vector<input_case> cases() {
    std::vector<input_case> result;
    struct model_case { std::string label; std::string value; outcome expected; };
    const std::vector<model_case> models = {
        {"omitted", "", outcome::delegate},
        {"canonical", "\"glm-5.3\"", outcome::delegate},
        {"native alias", "\"native-secondary\"", outcome::delegate},
        {"second alias", "\"declared-secondary\"", outcome::delegate},
        {"unknown", "\"unknown-model\"", outcome::unknown},
        {"different catalog model", "\"qwen3.8\"", outcome::unknown},
        {"case", "\"GLM-5.3\"", outcome::unknown},
        {"leading space", "\" glm-5.3\"", outcome::unknown},
        {"trailing space", "\"glm-5.3 \"", outcome::unknown},
        {"whitespace", "\" \\t\"", outcome::unknown},
        {"hidden path", "\"/data/models/model.gguf\"", outcome::unknown},
        {"empty", "\"\"", outcome::malformed_model},
        {"null", "null", outcome::malformed_model},
        {"true", "true", outcome::malformed_model},
        {"false", "false", outcome::malformed_model},
        {"integer", "35", outcome::malformed_model},
        {"float", "3.8", outcome::malformed_model},
        {"array", "[\"glm-5.3\"]", outcome::malformed_model},
        {"object", "{\"id\":\"glm-5.3\"}", outcome::malformed_model},
    };
    for (int stream = -1; stream <= 1; ++stream) {
        for (const auto & model : models) {
            std::string body = "{\"messages\":[],\"fixture\":\"unaltered\"";
            if (!model.value.empty()) { body += ",\"model\":" + model.value; }
            if (stream >= 0) { body += std::string(",\"stream\":") + (stream ? "true" : "false"); }
            body += "}";
            result.push_back({model.label + "/stream=" + std::to_string(stream), body, model.expected, stream == 1});
        }
        // Broken JSON includes the selected stream spelling, even though it cannot be interpreted.
        const auto broken = stream < 0 ? "{" : (stream ? "{\"stream\":true," : "{\"stream\":false,");
        result.push_back({"invalid JSON/stream=" + std::to_string(stream), broken, outcome::malformed_body, false});
        // A non-object cannot carry a top-level stream field; nested fields must not make it valid.
        const auto nonobject = stream < 0 ? "[]" : (stream ? "[{\"stream\":true}]" : "[{\"stream\":false}]");
        result.push_back({"non-object/stream=" + std::to_string(stream), nonobject, outcome::malformed_body, false});
    }
    for (const std::string & body : {"", "null", "true", "false", "35", "3.8", "\"glm-5.3\"", "{} {}"}) {
        result.push_back({"invalid/non-object " + body, body, outcome::malformed_body, false});
    }
    return result;
}

static void check_error(const std::string & data, outcome expected) {
    const auto body = json::parse(data);
    CHECK(body.is_object());
    CHECK(body.size() == 1);
    const auto & error = body.at("error");
    CHECK(error.is_object());
    CHECK(error.size() == 4);
    CHECK(error.at("type") == "invalid_request_error");
    CHECK(error.at("message").is_string());
    CHECK(!error.at("message").get<std::string>().empty());
    CHECK(error.at("message").get<std::string>().size() <= 128);
    if (expected == outcome::malformed_body) {
        CHECK(error.at("param").is_null());
    } else {
        CHECK(error.at("param") == "model");
    }
    if (expected == outcome::unknown) {
        CHECK(error.at("code").is_string());
        CHECK(error.at("code") == "model_not_found");
    } else {
        CHECK(error.at("code").is_null());
    }
    CHECK(data.find("[DONE]") == std::string::npos);
}

static void test_direct(const std::vector<input_case> & inputs) {
    fixture f;
    const std::function<bool()> should_stop = [] { return false; };
    for (const auto & path : paths) {
        for (const auto & input : inputs) {
            const auto before = f.downstream.snapshot();
            const auto session_before = f.downstream.session_snapshot();
            server_http_req req{{{"model", "glm-5.3"}}, {{"X-Conversation-Id", conversation}}, path,
                                "model=glm-5.3", input.body, {}, should_stop};
            auto res = f.http.handlers.at(path)(req);
            CHECK(res != nullptr);
            if (input.expected == outcome::delegate) {
                CHECK(f.downstream.last_request == &req);
                CHECK(f.downstream.last_response == res.get());
                CHECK(f.downstream.last_body == input.body);
                CHECK(f.downstream.last_path == path);
                CHECK(f.downstream.last_query == req.query_string);
                CHECK(f.downstream.last_headers == req.headers);
                CHECK(f.downstream.last_params == req.params);
                CHECK(res->status == 200);
                CHECK(res->is_stream() == input.stream);
                CHECK(f.downstream.snapshot().generator == before.generator + 1);
            } else {
                CHECK(res->status == 400);
                CHECK(!res->is_stream());
                CHECK(res->content_type == "application/json; charset=utf-8");
                CHECK(res->headers.empty());
                check_error(res->data, input.expected);
                CHECK(f.downstream.snapshot() == before);
                CHECK(f.downstream.session_snapshot() == session_before);
            }
        }
    }
    // Identity comes from metadata, including a different final-model fixture.
    int delegated = 0;
    auto alternate = server_chat_model_guard([&](const server_http_req &) -> server_http_res_ptr {
        ++delegated;
        return std::make_unique<server_http_res>();
    }, false, false, [] { return json::object({{"id", "qwen3.8"}, {"aliases", json::array()}}); });
    server_http_req req{{}, {}, paths[0], "", "{\"model\":\"qwen3.8\"}", {}, should_stop};
    CHECK(alternate(req)->status == 200);
    CHECK(delegated == 1);
    std::cout << "PASS: direct shipped guard/routes, " << inputs.size() * paths.size() << " matrix cases plus metadata-driven canonical\n";
}

static httplib::Headers headers(const std::string & credential = test_credential) {
    httplib::Headers result{{"X-Conversation-Id", conversation}};
    if (!credential.empty()) { result.emplace("Authorization", "Bearer " + credential); }
    return result;
}

static void check_json_http(const httplib::Result & res, int status) {
    CHECK(res);
    CHECK(res->status == status);
    CHECK(res->get_header_value("Content-Type") == "application/json; charset=utf-8");
    CHECK(!res->has_header("X-Accel-Buffering"));
    CHECK(res->get_header_value("Transfer-Encoding") != "chunked");
    CHECK(json::parse(res->body).is_object());
}

static void test_http(const std::vector<input_case> & inputs) {
    fixture f(false, false, true);
    httplib::Client client("127.0.0.1", f.http.port);
    client.set_connection_timeout(5);
    client.set_read_timeout(5);
    client.set_write_timeout(5);

    for (bool ready : {false, true}) {
        f.http.is_ready = ready;
        for (const auto & path : paths) {
            for (const auto & body : {"{\"model\":\"unknown\",\"stream\":true}", "null"}) {
                for (const auto & credential : {std::string(), std::string("wrong-test-fixture"), test_credential}) {
                    if (ready && credential == test_credential) { continue; }
                    const auto before = f.downstream.snapshot();
                    const int reads_before = f.metadata_reads;
                    const auto res = client.Post(path, headers(credential), body, "application/json");
                    check_json_http(res, ready ? 401 : 503);
                    const auto error = json::parse(res->body).at("error");
                    CHECK(error.at("code").is_number_integer());
                    CHECK(error.at("code") == (ready ? 401 : 503));
                    CHECK(error.at("type") == (ready ? "authentication_error" : "unavailable_error"));
                    CHECK(error.at("message") == (ready ? "Invalid API Key" : "Loading model"));
                    CHECK(f.metadata_reads == reads_before);
                    CHECK(f.downstream.snapshot() == before);
                }
            }
            const auto before = f.downstream.snapshot();
            const int reads_before = f.metadata_reads;
            const auto options = client.Options(path);
            CHECK(options);
            CHECK(options->status == 200);
            CHECK(options->body.empty());
            CHECK(options->get_header_value("Content-Type") == "text/html");
            CHECK(options->has_header("Access-Control-Allow-Methods"));
            CHECK(f.metadata_reads == reads_before);
            CHECK(f.downstream.snapshot() == before);
        }
    }

    for (const auto & path : paths) {
        for (const auto & input : inputs) {
            const auto before = f.downstream.snapshot();
            const auto session_before = f.downstream.session_snapshot();
            const auto res = client.Post(path + "?model=glm-5.3", headers(), input.body, "application/json");
            CHECK(res);
            if (input.expected == outcome::delegate) {
                CHECK(res->status == 200);
                CHECK(res->get_header_value("X-D3P-Delegated") == "yes");
                f.downstream.wait_for_complete(before.complete + 1);
                CHECK(f.downstream.snapshot().generator == before.generator + 1);
                if (input.stream) {
                    CHECK(res->get_header_value("Content-Type") == "text/event-stream");
                    CHECK(res->get_header_value("X-Accel-Buffering") == "no");
                    CHECK(res->body == "data: {\"model\":\"glm-5.3\",\"choices\":[]}\n\ndata: [DONE]\n\n");
                } else {
                    check_json_http(res, 200);
                    CHECK(json::parse(res->body).at("model") == canonical);
                }
                CHECK(f.downstream.last_body == input.body);
                CHECK(f.downstream.last_path == path);
                CHECK(f.downstream.last_query == "model=glm-5.3");
                CHECK(f.downstream.last_headers.at("X-Conversation-Id") == conversation);
            } else {
                check_json_http(res, 400);
                CHECK(!res->has_header("X-D3P-Delegated"));
                check_error(res->body, input.expected);
                CHECK(f.downstream.snapshot() == before);
                CHECK(f.downstream.session_snapshot() == session_before);
            }
        }
    }
    const auto missing = client.Get("/d3p-missing-route", headers());
    check_json_http(missing, 404);
    CHECK(missing->body == "{\"error\":{\"message\":\"File Not Found\",\"type\":\"not_found_error\",\"code\":404}}");
    // An unrelated endpoint is not registered by the new route helper.
    CHECK(f.http.handlers.count("/v1/completions") == 0);
    std::cout << "PASS: pinned loopback HTTP serialization, " << inputs.size() * paths.size()
              << " matrix cases; auth/readiness/OPTIONS order and exact stock 404\n";
}

static void test_bypass(const std::vector<input_case> & inputs) {
    for (const auto & mode : {std::pair<bool, bool>{true, false}, {false, true}, {true, true}}) {
        fixture f(mode.first, mode.second, true);
        f.http.is_ready = true;
        httplib::Client client("127.0.0.1", f.http.port);
        client.set_read_timeout(5);
        for (const auto & path : paths) {
            for (const auto & input : inputs) {
                const auto before = f.downstream.snapshot();
                const auto res = client.Post(path, headers(), input.body, "application/json");
                CHECK(res);
                CHECK(res->status == 200);
                CHECK(res->get_header_value("X-D3P-Delegated") == "yes");
                f.downstream.wait_for_complete(before.complete + 1);
                CHECK(f.downstream.snapshot().generator == before.generator + 1);
                CHECK(f.downstream.last_body == input.body);
                CHECK(f.metadata_reads == 0);
            }
            const auto before = f.downstream.snapshot();
            const auto alias = client.Post(path, headers(), "{\"model\":\"router-valid-child-unknown\",\"stream\":true}", "application/json");
            CHECK(alias);
            CHECK(alias->status == 200);
            f.downstream.wait_for_complete(before.complete + 1);
            CHECK(alias->get_header_value("Content-Type") == "text/event-stream");
            CHECK(f.metadata_reads == 0);
        }
    }
    std::cout << "PASS: router/child/both modes bypass all " << inputs.size() * paths.size() * 3
              << " cases and router-valid child-unknown alias\n";
}

int main() {
    try {
        CHECK(std::getenv("AIP_MODE") == nullptr);
        const auto inputs = cases();
        test_direct(inputs);
        test_http(inputs);
        test_bypass(inputs);
        std::cout << "PASS: D3P focused native tests (fake downstream, no model loaded)\n";
        return 0;
    } catch (const std::exception & error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
