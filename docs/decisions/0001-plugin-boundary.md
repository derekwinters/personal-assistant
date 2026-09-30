# 0001 — Plugin boundary

- **Status:** Proposed
- **Issue:** #18 (part of #4)

## Context

Every integration in #4 is parked on one question: what a plugin physically is. This note answers
only that question, so the first feature, reminders (#8), can be built against it. The other
questions in #4 stay open (see [Not settled here](#not-settled-here)).

The known integrations (#5–#13) split into three kinds:

| Kind | Integrations | What reaching it takes |
| --- | --- | --- |
| Built into the assistant | reminders #8, water #9, meals #10, calendar #7 | Nothing: the code lives here. The calendar reads the on-device calendar provider. |
| Separate Android app on the phone | interval trainer #5, future meal planning app #12 | On-device IPC. |
| Service reached over the network | chores backend #6, LAN AI model #13, possibly Google Keep #11 | HTTP. |

Reading the interval trainer and chores repositories settles which transport each existing app
needs:

- **Interval trainer (#5)** is fully local, with no server. Today it exposes nothing to other
  apps: only its launcher activity is exported, and its workout service is not. It keeps no
  workout history yet. The assistant can only reach it through on-device IPC, and that needs a
  change in the trainer's repository. Its release signing key is fixed permanently.
- **Chores (#6)** is a thin Android client over a self-hosted backend with a versioned REST API
  (`/v1`: list chores, complete, skip, reassign, notifications). The assistant should talk to the
  backend over HTTP, not to the chores app.

## Options

### A. In-process Kotlin modules only

Every plugin is a Gradle module compiled into the assistant.

- **Cost to build:** lowest. Plain Kotlin calls, one build, one test suite.
- **Fit with #5–#13:** good for #7–#10. HTTP services (#6, #13, #11) still work, because an
  in-process module can make HTTP calls. **It cannot reach the interval trainer (#5)** or a
  separate meal planning app (#12): their data and actions live in another app's process.
- **Forces on reminders (#8):** nothing beyond a module and an interface.

### B. Separate Android apps over IPC only

Every plugin is its own APK, talking to the assistant through a bound service, content provider or
intents.

- **Cost to build:** highest. Every plugin needs its own app, packaging, signing, install and
  update path, plus an IPC layer, caller verification, and Android 11+ package-visibility rules.
- **Fit with #5–#13:** natural for #5 and #12. Poor for everything else: water, reminders, meals
  and calendar become separate apps for no gain, and the HTTP services need a wrapper app just to
  hold the HTTP client.
- **Forces on reminders (#8):** the first feature has to ship as a second APK, so the whole IPC
  contract, discovery and trust scheme must exist before the first reminder fires.

### C. A mix: one contract, three transports

One data-only plugin contract in a pure-Kotlin `:plugin-api` module. The core never cares how a
plugin is reached; three transports sit behind the same contract:

1. **In-process modules** for built-in features: reminders #8, water #9, meals #10, calendar #7.
2. **Companion Android apps** for #5 and #12, through an exported content provider using
   `ContentProvider.call(method, arg, extras)` with a JSON payload, plus a small SDK library the
   companion app includes.
3. **An HTTP bridge**, an in-process adapter mapping a REST API onto the contract, for the chores
   backend #6, the LAN AI model #13, and possibly Keep #11.

- **Cost to build:** A's cost for built-in features; IPC is paid only when #5 or #12 is built.
- **Fit with #5–#13:** every known integration has a transport, and none pays for one it does not
  need.
- **Forces on reminders (#8):** built in-process like A. #8 does not wait on the companion or HTTP
  transports, but it does need `:plugin-api` and a plugin registry first, so it is written against
  the contract rather than wired into the core.

## Recommendation

**C.** A cannot reach the interval trainer, which is one of the two first-party apps that motivated
the plugin architecture. B makes the simplest features (water, reminders) pay for IPC they never
use, and makes the first feature wait on all of it. C costs the same as A until a companion app is
actually integrated, and keeps one contract, so moving a plugin between transports later does not
change the core.

Why a content provider's `call()` for companion apps, rather than AIDL or a bound service: it is
synchronous, has no binding lifecycle to manage, identifies the caller with `getCallingPackage()`,
and its IPC surface stays the same however the contract grows, because new methods travel as data.
Companion apps are found by an intent action declared in their manifest, with a matching
`<queries>` entry in the assistant (Android 11+). An action that needs UI, such as starting a
workout, hands off to the companion app by deep link, because Android 12+ blocks starting a
foreground service from the background.

What C would mean for the code, as a sketch for the follow-up specifications rather than part of
this decision:

- The core owns the registry, scheduling, notifications, shared data, settings and home cards.
  Plugins never post notifications or draw UI themselves, and never call each other.
- Suggested invariants: the core never imports a plugin module; a plugin module depends on
  `:plugin-api` and no other project module; only the core schedules work or posts notifications;
  a companion app is not enabled until its signing certificate matches an allowlist.
- All plugins are compiled into every build and enabled per plugin at runtime; a disabled plugin
  does nothing. No build flavours.
- For #8: `:plugin-api` and the registry first (proved with a fake plugin on the home screen), then
  the core scheduler and notifications with reminders as the first real plugin.

## Decision

Pending the owner's decision.

## Consequences

To be written once the decision is recorded.

## Not settled here

Deliberately left open, as follow-ups to #4:

- **The plugin contract:** what a plugin declares (feeds, actions, schedules, settings,
  permissions) and how it is versioned.
- **Discovery and lifecycle:** how plugins are found, enabled, configured and disabled.
- **Shared data:** which data belongs to the core versus a plugin.
- **Scheduling ownership** in detail, including whether #8's scheduler is core (the sketch above
  assumes so).
- **Companion trust:** the exact mechanism, for example a signing-certificate allowlist checked in
  both directions. A signature permission would need one shared key, which the trainer's fixed key
  rules out.
- **Chores notifications:** the chores app already polls and posts its own notifications, so who
  notifies about chores needs deciding to avoid notifying twice.
- **Chores auth:** the backend issues only a full-user, year-long token; whether the assistant
  stores one or the backend gains a scoped token.
- **Publishing the companion SDK** for other repositories to depend on.
- **Where the grocery list lives:** Google Keep (#11) or the future meal planning app (#12).
- **Auth and Android permissions** per plugin, and **AI orchestration** (#13): what the model sees
  and may call.
