#include <clap/clap.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef long (*engine_create_fn)(char *, char *);
typedef long (*engine_compile_fn)(long, char *);
typedef char *(*engine_error_fn)(long);
typedef double (*engine_milliseconds_fn)(long);
typedef void (*engine_destroy_fn)(long);
typedef float (*process_fn)(float);

static double now_seconds(void) {
  struct timespec time;
  clock_gettime(CLOCK_MONOTONIC_RAW, &time);
  return (double)time.tv_sec + (double)time.tv_nsec / 1000000000.0;
}

static double benchmark_process(process_fn fn) {
  volatile float sample = 0.8f;
  const int iterations = 10000000;
  const double started = now_seconds();
  for (int i = 0; i < iterations; ++i)
    sample = fn(sample);
  const double elapsed = now_seconds() - started;
  if (sample == 123456.0f)
    puts("unreachable");
  return elapsed * 1000000000.0 / (double)iterations;
}

static const void *host_extension(const clap_host_t *host, const char *id) {
  (void)host;
  (void)id;
  return NULL;
}

static void host_request_restart(const clap_host_t *host) { (void)host; }
static void host_request_process(const clap_host_t *host) { (void)host; }
static void host_request_callback(const clap_host_t *host) { (void)host; }

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: smoke-host <Metacarp binary>\n");
    return 2;
  }
  void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (!library) {
    fprintf(stderr, "dlopen: %s\n", dlerror());
    return 3;
  }
  const clap_plugin_entry_t *entry = dlsym(library, "clap_entry");
  if (!entry || !entry->init(argv[1]))
    return 4;
  const clap_plugin_factory_t *factory =
      entry->get_factory(CLAP_PLUGIN_FACTORY_ID);
  if (!factory || factory->get_plugin_count(factory) != 1)
    return 5;
  const clap_plugin_descriptor_t *descriptor =
      factory->get_plugin_descriptor(factory, 0);
  if (!descriptor || strcmp(descriptor->id, "org.carpentry.metacarp"))
    return 6;

  const clap_host_t host = {
      .clap_version = CLAP_VERSION_INIT,
      .host_data = NULL,
      .name = "Metacarp smoke host",
      .vendor = "Carpentry",
      .url = "",
      .version = "0",
      .get_extension = host_extension,
      .request_restart = host_request_restart,
      .request_process = host_request_process,
      .request_callback = host_request_callback,
  };
  const clap_plugin_t *plugin =
      factory->create_plugin(factory, &host, descriptor->id);
  if (!plugin || !plugin->init(plugin) ||
      !plugin->activate(plugin, 48000.0, 16, 16) ||
      !plugin->start_processing(plugin))
    return 7;

  float left[] = {0.25f, -0.5f};
  float right[] = {0.75f, -1.0f};
  float out_left[] = {0.0f, 0.0f};
  float out_right[] = {0.0f, 0.0f};
  float *inputs[] = {left, right};
  float *outputs[] = {out_left, out_right};
  clap_audio_buffer_t input = {.data32 = inputs, .channel_count = 2};
  clap_audio_buffer_t output = {.data32 = outputs, .channel_count = 2};
  clap_process_t process = {
      .frames_count = 2,
      .audio_inputs = &input,
      .audio_outputs = &output,
      .audio_inputs_count = 1,
      .audio_outputs_count = 1,
  };
  if (plugin->process(plugin, &process) != CLAP_PROCESS_CONTINUE ||
      out_left[0] != left[0] || out_right[1] != right[1])
    return 8;

  plugin->stop_processing(plugin);
  plugin->deactivate(plugin);
  plugin->destroy(plugin);

  engine_create_fn engine_create = dlsym(library, "metacarp_engine_create");
  engine_compile_fn engine_compile = dlsym(library, "metacarp_engine_compile");
  engine_error_fn engine_error = dlsym(library, "metacarp_engine_error");
  engine_milliseconds_fn engine_milliseconds =
      dlsym(library, "metacarp_engine_milliseconds");
  engine_destroy_fn engine_destroy = dlsym(library, "metacarp_engine_destroy");
  if (!engine_create || !engine_compile || !engine_error ||
      !engine_milliseconds || !engine_destroy)
    return 9;
  char core[4096];
  snprintf(core, sizeof(core), "%s", argv[1]);
  char *bundle = strstr(core, ".clap");
  if (!bundle)
    return 10;
  bundle += strlen(".clap");
  *bundle = '\0';
  strncat(core, "/Contents/Resources/core", sizeof(core) - strlen(core) - 1);
  char scratch[] = "/tmp/metacarp-engine-smoke-XXXXXX";
  if (!mkdtemp(scratch))
    return 11;
  long engine = engine_create(core, scratch);
  long identity_address = engine_compile(
      engine, "(sig process (Fn [Float] Float))\n(defn process [x] x)");
  const double identity_ms = engine_milliseconds(engine);
  long gain_address = engine_compile(
      engine,
      "(sig process (Fn [Float] Float))\n"
      "(defn process [x] (Float.* x 0.5f))");
  const double gain_ms = engine_milliseconds(engine);
  if (!identity_address || !gain_address ||
      ((process_fn)identity_address)(0.8f) != 0.8f ||
      ((process_fn)gain_address)(0.8f) != 0.4f)
    return 12;
  if (engine_compile(
          engine,
          "(sig process (Fn [Float] Float))\n"
          "(defn process [x] (no-such-function x))") != 0 ||
      ((process_fn)gain_address)(0.8f) != 0.4f ||
      ((process_fn)identity_address)(0.8f) != 0.8f)
    return 13;
  char *error = engine_error(engine);
  if (!error || !*error)
    return 14;
  free(error);
  printf("compile: identity %.1f ms, gain %.1f ms\n", identity_ms, gain_ms);
  printf("JIT scalar call: %.2f ns/sample\n",
         benchmark_process((process_fn)gain_address));
  engine_destroy(engine);
  entry->deinit();
  dlclose(library);
  puts("Metacarp CLAP smoke test passed");
  return 0;
}
