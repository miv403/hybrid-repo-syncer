# hybrid syncer

`hybrid-syncer` is a lightweight Python CLI wrapper around [Copybara](https://github.com/google/copybara). It simplifies multi-repository code synchronization by reading a declarative YAML manifest (`sync-manifest.yaml`), automatically generating Copybara Starlark (`copy.bara.sky`) configuration files, executing `push`, `pull`, `status`, and `doctor` operations.

<img src="img/diagram.png" width="500 px">
