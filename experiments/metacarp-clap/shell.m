#import <Cocoa/Cocoa.h>

#include <clap/clap.h>
#include <clap/ext/audio-ports.h>
#include <clap/ext/gui.h>

#include <dlfcn.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern void carp_init_globals(int argc, char **argv);
extern long metacarp_engine_create(char *core_dir, char *scratch);
extern long metacarp_engine_compile(long engine, char *source);
extern char *metacarp_engine_error(long engine);
extern double metacarp_engine_milliseconds(long engine);
extern void metacarp_engine_destroy(long engine);

typedef float (*metacarp_process_fn)(float);

static char g_core_dir[4096];
static void *g_self_handle;
static pthread_mutex_t g_compile_lock = PTHREAD_MUTEX_INITIALIZER;

typedef struct metacarp_plugin {
  clap_plugin_t plugin;
  const clap_host_t *host;
  _Atomic(uintptr_t) process_address;

  pthread_t worker;
  pthread_mutex_t lock;
  pthread_cond_t wake;
  bool stopping;
  char *pending_source;
  unsigned long pending_revision;
  long engine;
  char scratch[1024];

  char *status;
  double compile_ms;
  void *view_controller;
} metacarp_plugin_t;

static const char *kInitialSource =
    "(sig process (Fn [Float] Float))\n"
    "(defn process [x]\n"
    "  x)\n";

static void metacarp_set_status(metacarp_plugin_t *plug, const char *status,
                                double milliseconds) {
  pthread_mutex_lock(&plug->lock);
  free(plug->status);
  plug->status = strdup(status ? status : "");
  plug->compile_ms = milliseconds;
  pthread_mutex_unlock(&plug->lock);
}

static void metacarp_request_compile(metacarp_plugin_t *plug,
                                     const char *source) {
  pthread_mutex_lock(&plug->lock);
  free(plug->pending_source);
  plug->pending_source = strdup(source ? source : "");
  ++plug->pending_revision;
  pthread_cond_signal(&plug->wake);
  pthread_mutex_unlock(&plug->lock);
}

static void *metacarp_worker_main(void *context) {
  metacarp_plugin_t *plug = context;
  pthread_mutex_lock(&g_compile_lock);
  plug->engine = metacarp_engine_create(g_core_dir, plug->scratch);
  pthread_mutex_unlock(&g_compile_lock);

  for (;;) {
    pthread_mutex_lock(&plug->lock);
    while (!plug->stopping && !plug->pending_source)
      pthread_cond_wait(&plug->wake, &plug->lock);
    if (plug->stopping) {
      pthread_mutex_unlock(&plug->lock);
      break;
    }
    char *source = plug->pending_source;
    plug->pending_source = NULL;
    pthread_mutex_unlock(&plug->lock);

    metacarp_set_status(plug, "compiling…", 0.0);
    pthread_mutex_lock(&g_compile_lock);
    const long address = metacarp_engine_compile(plug->engine, source);
    const double elapsed = metacarp_engine_milliseconds(plug->engine);
    char *error = address == 0 ? metacarp_engine_error(plug->engine) : NULL;
    pthread_mutex_unlock(&g_compile_lock);
    free(source);

    if (address != 0) {
      atomic_store_explicit(&plug->process_address, (uintptr_t)address,
                            memory_order_release);
      metacarp_set_status(plug, "compiled", elapsed);
    } else {
      metacarp_set_status(plug, error, elapsed);
      free(error);
    }
  }
  return NULL;
}

@interface MetacarpViewController : NSObject {
@public
  metacarp_plugin_t *_plug;
  NSView *_root;
  NSTextView *_editor;
  NSTextField *_status;
  NSTimer *_timer;
}
- (instancetype)initWithPlugin:(metacarp_plugin_t *)plug;
- (void)compile:(id)sender;
- (void)poll:(NSTimer *)timer;
@end

@implementation MetacarpViewController
- (instancetype)initWithPlugin:(metacarp_plugin_t *)plug {
  if (!(self = [super init]))
    return nil;
  _plug = plug;
  _root = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 640, 420)];

  NSScrollView *scroll = [[NSScrollView alloc]
      initWithFrame:NSMakeRect(12, 76, 616, 332)];
  [scroll setHasVerticalScroller:YES];
  [scroll setBorderType:NSBezelBorder];
  _editor = [[NSTextView alloc] initWithFrame:[[scroll contentView] bounds]];
  [_editor setAutoresizingMask:NSViewWidthSizable | NSViewHeightSizable];
  [_editor setFont:[NSFont monospacedSystemFontOfSize:14 weight:NSFontWeightRegular]];
  [_editor setString:[NSString stringWithUTF8String:kInitialSource]];
  [scroll setDocumentView:_editor];
  [_root addSubview:scroll];
  [scroll release];

  NSButton *button = [[NSButton alloc] initWithFrame:NSMakeRect(12, 12, 88, 28)];
  [button setTitle:@"Compile"];
  [button setBezelStyle:NSBezelStyleRounded];
  [button setTarget:self];
  [button setAction:@selector(compile:)];
  [_root addSubview:button];
  [button release];

  _status = [[NSTextField alloc] initWithFrame:NSMakeRect(112, 8, 516, 56)];
  [_status setEditable:NO];
  [_status setBordered:NO];
  [_status setDrawsBackground:NO];
  [_status setLineBreakMode:NSLineBreakByWordWrapping];
  [[_status cell] setWraps:YES];
  [_status setStringValue:@"identity fallback; compiling initial buffer…"];
  [_root addSubview:_status];

  _timer = [NSTimer scheduledTimerWithTimeInterval:0.1
                                            target:self
                                          selector:@selector(poll:)
                                          userInfo:nil
                                           repeats:YES];
  return self;
}

- (void)compile:(id)sender {
  (void)sender;
  metacarp_request_compile(_plug, [[_editor string] UTF8String]);
}

- (void)poll:(NSTimer *)timer {
  (void)timer;
  pthread_mutex_lock(&_plug->lock);
  char *text = strdup(_plug->status ? _plug->status : "");
  double elapsed = _plug->compile_ms;
  pthread_mutex_unlock(&_plug->lock);
  NSString *rendered = elapsed > 0.0
                           ? [NSString stringWithFormat:@"%s (%.1f ms)", text,
                                                        elapsed]
                           : [NSString stringWithUTF8String:text];
  [_status setStringValue:rendered];
  free(text);
}

- (void)dealloc {
  [_timer invalidate];
  [_status release];
  [_editor release];
  [_root release];
  [super dealloc];
}
@end

static uint32_t metacarp_audio_ports_count(const clap_plugin_t *plugin,
                                           bool is_input) {
  (void)plugin;
  (void)is_input;
  return 1;
}

static bool metacarp_audio_ports_get(const clap_plugin_t *plugin,
                                     uint32_t index, bool is_input,
                                     clap_audio_port_info_t *info) {
  (void)plugin;
  (void)is_input;
  if (index != 0)
    return false;
  info->id = 0;
  snprintf(info->name, sizeof(info->name), "%s", "Stereo");
  info->channel_count = 2;
  info->flags = CLAP_AUDIO_PORT_IS_MAIN;
  info->port_type = CLAP_PORT_STEREO;
  info->in_place_pair = CLAP_INVALID_ID;
  return true;
}

static const clap_plugin_audio_ports_t kAudioPorts = {
    .count = metacarp_audio_ports_count,
    .get = metacarp_audio_ports_get,
};

static clap_process_status metacarp_process(const clap_plugin_t *plugin,
                                            const clap_process_t *process) {
  metacarp_plugin_t *plug = plugin->plugin_data;
  const uintptr_t address = atomic_load_explicit(&plug->process_address,
                                                  memory_order_acquire);
  const metacarp_process_fn fn = (metacarp_process_fn)address;
  if (process->audio_inputs_count == 0 || process->audio_outputs_count == 0)
    return CLAP_PROCESS_CONTINUE;

  const clap_audio_buffer_t *input = &process->audio_inputs[0];
  clap_audio_buffer_t *output = &process->audio_outputs[0];
  const uint32_t channels = input->channel_count < output->channel_count
                                ? input->channel_count
                                : output->channel_count;
  for (uint32_t channel = 0; channel < channels; ++channel) {
    const float *in = input->data32[channel];
    float *out = output->data32[channel];
    if (!in || !out)
      continue;
    if (fn) {
      for (uint32_t frame = 0; frame < process->frames_count; ++frame)
        out[frame] = fn(in[frame]);
    } else if (out != in) {
      memcpy(out, in, process->frames_count * sizeof(float));
    }
  }
  return CLAP_PROCESS_CONTINUE;
}

static bool metacarp_gui_is_api_supported(const clap_plugin_t *plugin,
                                          const char *api, bool floating) {
  (void)plugin;
  return !floating && api && !strcmp(api, CLAP_WINDOW_API_COCOA);
}

static bool metacarp_gui_get_preferred_api(const clap_plugin_t *plugin,
                                           const char **api, bool *floating) {
  (void)plugin;
  *api = CLAP_WINDOW_API_COCOA;
  *floating = false;
  return true;
}

static bool metacarp_gui_create(const clap_plugin_t *plugin, const char *api,
                                bool floating) {
  if (!metacarp_gui_is_api_supported(plugin, api, floating))
    return false;
  metacarp_plugin_t *plug = plugin->plugin_data;
  if (plug->view_controller)
    return false;
  plug->view_controller = [[MetacarpViewController alloc] initWithPlugin:plug];
  return plug->view_controller != NULL;
}

static void metacarp_gui_destroy(const clap_plugin_t *plugin) {
  metacarp_plugin_t *plug = plugin->plugin_data;
  MetacarpViewController *controller = plug->view_controller;
  if (!controller)
    return;
  [controller->_root removeFromSuperview];
  [controller release];
  plug->view_controller = NULL;
}

static bool metacarp_gui_set_scale(const clap_plugin_t *plugin, double scale) {
  (void)plugin;
  (void)scale;
  return false;
}

static bool metacarp_gui_get_size(const clap_plugin_t *plugin, uint32_t *width,
                                  uint32_t *height) {
  (void)plugin;
  *width = 640;
  *height = 420;
  return true;
}

static bool metacarp_gui_can_resize(const clap_plugin_t *plugin) {
  (void)plugin;
  return false;
}

static bool metacarp_gui_get_resize_hints(const clap_plugin_t *plugin,
                                          clap_gui_resize_hints_t *hints) {
  (void)plugin;
  (void)hints;
  return false;
}

static bool metacarp_gui_adjust_size(const clap_plugin_t *plugin,
                                     uint32_t *width, uint32_t *height) {
  (void)plugin;
  *width = 640;
  *height = 420;
  return true;
}

static bool metacarp_gui_set_size(const clap_plugin_t *plugin, uint32_t width,
                                  uint32_t height) {
  (void)plugin;
  return width == 640 && height == 420;
}

static bool metacarp_gui_set_parent(const clap_plugin_t *plugin,
                                    const clap_window_t *window) {
  metacarp_plugin_t *plug = plugin->plugin_data;
  MetacarpViewController *controller = plug->view_controller;
  if (!controller || !window || strcmp(window->api, CLAP_WINDOW_API_COCOA))
    return false;
  NSView *parent = (NSView *)window->cocoa;
  [parent addSubview:controller->_root];
  return true;
}

static bool metacarp_gui_set_transient(const clap_plugin_t *plugin,
                                       const clap_window_t *window) {
  (void)plugin;
  (void)window;
  return false;
}

static void metacarp_gui_suggest_title(const clap_plugin_t *plugin,
                                       const char *title) {
  (void)plugin;
  (void)title;
}

static bool metacarp_gui_show(const clap_plugin_t *plugin) {
  metacarp_plugin_t *plug = plugin->plugin_data;
  MetacarpViewController *controller = plug->view_controller;
  if (!controller)
    return false;
  [controller->_root setHidden:NO];
  return true;
}

static bool metacarp_gui_hide(const clap_plugin_t *plugin) {
  metacarp_plugin_t *plug = plugin->plugin_data;
  MetacarpViewController *controller = plug->view_controller;
  if (!controller)
    return false;
  [controller->_root setHidden:YES];
  return true;
}

static const clap_plugin_gui_t kGui = {
    .is_api_supported = metacarp_gui_is_api_supported,
    .get_preferred_api = metacarp_gui_get_preferred_api,
    .create = metacarp_gui_create,
    .destroy = metacarp_gui_destroy,
    .set_scale = metacarp_gui_set_scale,
    .get_size = metacarp_gui_get_size,
    .can_resize = metacarp_gui_can_resize,
    .get_resize_hints = metacarp_gui_get_resize_hints,
    .adjust_size = metacarp_gui_adjust_size,
    .set_size = metacarp_gui_set_size,
    .set_parent = metacarp_gui_set_parent,
    .set_transient = metacarp_gui_set_transient,
    .suggest_title = metacarp_gui_suggest_title,
    .show = metacarp_gui_show,
    .hide = metacarp_gui_hide,
};

static bool metacarp_init(const clap_plugin_t *plugin) {
  metacarp_plugin_t *plug = plugin->plugin_data;
  metacarp_request_compile(plug, kInitialSource);
  return true;
}

static void metacarp_destroy(const clap_plugin_t *plugin) {
  metacarp_plugin_t *plug = plugin->plugin_data;
  if (plug->view_controller)
    metacarp_gui_destroy(plugin);
  pthread_mutex_lock(&plug->lock);
  plug->stopping = true;
  pthread_cond_signal(&plug->wake);
  pthread_mutex_unlock(&plug->lock);
  pthread_join(plug->worker, NULL);
  if (plug->engine) {
    pthread_mutex_lock(&g_compile_lock);
    metacarp_engine_destroy(plug->engine);
    pthread_mutex_unlock(&g_compile_lock);
  }
  pthread_cond_destroy(&plug->wake);
  pthread_mutex_destroy(&plug->lock);
  free(plug->pending_source);
  free(plug->status);
  free(plug);
}

static bool metacarp_activate(const clap_plugin_t *plugin, double sample_rate,
                              uint32_t min_frames, uint32_t max_frames) {
  (void)plugin;
  (void)sample_rate;
  (void)min_frames;
  (void)max_frames;
  return true;
}

static void metacarp_deactivate(const clap_plugin_t *plugin) { (void)plugin; }
static bool metacarp_start_processing(const clap_plugin_t *plugin) {
  (void)plugin;
  return true;
}
static void metacarp_stop_processing(const clap_plugin_t *plugin) {
  (void)plugin;
}
static void metacarp_reset(const clap_plugin_t *plugin) { (void)plugin; }
static void metacarp_on_main_thread(const clap_plugin_t *plugin) {
  (void)plugin;
}

static const void *metacarp_get_extension(const clap_plugin_t *plugin,
                                          const char *id) {
  (void)plugin;
  if (!strcmp(id, CLAP_EXT_AUDIO_PORTS))
    return &kAudioPorts;
  if (!strcmp(id, CLAP_EXT_GUI))
    return &kGui;
  return NULL;
}

static const char *kFeatures[] = {CLAP_PLUGIN_FEATURE_AUDIO_EFFECT,
                                  CLAP_PLUGIN_FEATURE_STEREO, NULL};
static const clap_plugin_descriptor_t kDescriptor = {
    .clap_version = CLAP_VERSION_INIT,
    .id = "org.carpentry.metacarp",
    .name = "Metacarp",
    .vendor = "Carpentry",
    .url = "https://github.com/carpentry-org",
    .manual_url = "",
    .support_url = "",
    .version = "0.0.1",
    .description = "Audio in, one live-compiled Carp function, audio out.",
    .features = kFeatures,
};

static const clap_plugin_t *metacarp_create(const clap_host_t *host) {
  if (!clap_version_is_compatible(host->clap_version))
    return NULL;
  metacarp_plugin_t *plug = calloc(1, sizeof(*plug));
  plug->host = host;
  atomic_init(&plug->process_address, 0);
  pthread_mutex_init(&plug->lock, NULL);
  pthread_cond_init(&plug->wake, NULL);
  plug->status = strdup("starting compiler…");
  snprintf(plug->scratch, sizeof(plug->scratch),
           "/tmp/metacarp-clap-%d-XXXXXX", getpid());
  if (!mkdtemp(plug->scratch)) {
    free(plug->status);
    free(plug);
    return NULL;
  }

  plug->plugin.desc = &kDescriptor;
  plug->plugin.plugin_data = plug;
  plug->plugin.init = metacarp_init;
  plug->plugin.destroy = metacarp_destroy;
  plug->plugin.activate = metacarp_activate;
  plug->plugin.deactivate = metacarp_deactivate;
  plug->plugin.start_processing = metacarp_start_processing;
  plug->plugin.stop_processing = metacarp_stop_processing;
  plug->plugin.reset = metacarp_reset;
  plug->plugin.process = metacarp_process;
  plug->plugin.get_extension = metacarp_get_extension;
  plug->plugin.on_main_thread = metacarp_on_main_thread;
  if (pthread_create(&plug->worker, NULL, metacarp_worker_main, plug) != 0) {
    free(plug->status);
    free(plug);
    return NULL;
  }
  return &plug->plugin;
}

static uint32_t factory_count(const clap_plugin_factory_t *factory) {
  (void)factory;
  return 1;
}

static const clap_plugin_descriptor_t *
factory_descriptor(const clap_plugin_factory_t *factory, uint32_t index) {
  (void)factory;
  return index == 0 ? &kDescriptor : NULL;
}

static const clap_plugin_t *factory_create(const clap_plugin_factory_t *factory,
                                           const clap_host_t *host,
                                           const char *plugin_id) {
  (void)factory;
  return !strcmp(plugin_id, kDescriptor.id) ? metacarp_create(host) : NULL;
}

static const clap_plugin_factory_t kFactory = {
    .get_plugin_count = factory_count,
    .get_plugin_descriptor = factory_descriptor,
    .create_plugin = factory_create,
};

static bool entry_init(const char *plugin_path) {
  char binary[4096];
  snprintf(binary, sizeof(binary), "%s", plugin_path ? plugin_path : "");
  snprintf(g_core_dir, sizeof(g_core_dir), "%s", binary);
  char *bundle = strstr(g_core_dir, ".clap");
  if (bundle) {
    bundle += strlen(".clap");
    *bundle = '\0';
    strncat(g_core_dir, "/Contents/Resources/core",
            sizeof(g_core_dir) - strlen(g_core_dir) - 1);
  }
  if (strstr(binary, ".clap") && !strstr(binary, "/Contents/MacOS/"))
    strncat(binary, "/Contents/MacOS/Metacarp",
            sizeof(binary) - strlen(binary) - 1);
  g_self_handle = dlopen(binary, RTLD_NOW | RTLD_GLOBAL);
  if (!g_self_handle)
    return false;
  carp_init_globals(0, NULL);
  return access(g_core_dir, R_OK) == 0;
}

static void entry_deinit(void) {
  if (g_self_handle) {
    dlclose(g_self_handle);
    g_self_handle = NULL;
  }
}

static const void *entry_get_factory(const char *factory_id) {
  return !strcmp(factory_id, CLAP_PLUGIN_FACTORY_ID) ? &kFactory : NULL;
}

CLAP_EXPORT const clap_plugin_entry_t clap_entry = {
    .clap_version = CLAP_VERSION_INIT,
    .init = entry_init,
    .deinit = entry_deinit,
    .get_factory = entry_get_factory,
};
