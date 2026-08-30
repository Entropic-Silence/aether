# Plugin Protocol

Everything behind an interface; plugins register concrete providers.

## What a plugin can register

Models, tools, skills, search providers, sandbox providers, storage, image
providers, agent runtimes, and UI extensions.

## Manifest (`plugin.yaml`)

```yaml
api_version: 1            # Plugin API is versioned for backward compatibility
id: com.example.search-brave
name: Brave Search
version: 1.2.0
permissions: [network:api.brave.com]
entrypoint: dist/index.js
dependencies: []
capabilities: [search]
```

## Skill engine (not "just a prompt")

```
Skill {
  name, version, description, instructions, trigger,
  capabilities[], allowed_models[], allowed_tools[],
  input_schema, output_schema, priority, enabled,
  scope: global|workspace|project|user|model|tool|image_model
}
```

Sources: built-in, file, git, plugin, marketplace. Skills are versioned,
import/export-able, testable, and scoped. Image models bind a **prompt skill**
that tells the optimizer what the model is good at.

## Prompt management

System prompts live in the DB with versioning: draft → publish → rollback →
compare, scoped by model/workspace. Core prompts are not scattered in code.

## Plugin security

Declared `permissions` are enforced; a plugin may only touch what its
manifest allows. Secrets are injected by the platform, never read from other
plugins.
