# Using Multiple Knowledge Repositories with LightRAG

This document explains how to use LightRAG with multiple separate knowledge repositories, each with its own documents and graph database.

## Why Use Multiple Repositories?

1. **Topic Isolation**: Keep unrelated topics separate to prevent semantic contamination
2. **Project Management**: Separate repositories for different projects or clients
3. **Testing & Development**: Maintain separate development and production repositories
4. **Memory Optimization**: Smaller repositories are more efficient to query

## Creating and Using Multiple Repositories

LightRAG now supports specifying custom working and input directories when starting the server. This allows you to maintain completely separate knowledge bases.

### Basic Usage

Start LightRAG with custom directories:

```bash
# Start LightRAG with a custom repository for project1
./start.sh --working-dir ./data/project1_storage --input-dir ./data/project1_inputs
```

The script will:
1. Create the directories if they don't exist
2. Mount them in the Docker container
3. Configure LightRAG to use these paths

### Example Repository Structure

```
/data
  /default_storage     # Default repository
  /default_inputs
  /project1_storage    # Project 1 repository
  /project1_inputs
  /project2_storage    # Project 2 repository 
  /project2_inputs
```

### Creating Shell Scripts for Different Repositories

For convenience, you can create shell scripts for each repository:

1. Create `start_project1.sh`:

```bash
#!/bin/bash
./start.sh --working-dir ./data/project1_storage --input-dir ./data/project1_inputs
```

2. Create `start_project2.sh`:

```bash
#!/bin/bash
./start.sh --working-dir ./data/project2_storage --input-dir ./data/project2_inputs
```

3. Make them executable:

```bash
chmod +x start_project1.sh start_project2.sh
```

## Notes and Considerations

- **Server Port**: By default, all repositories use port 9621. If you want to run multiple repositories simultaneously, modify the port in the start scripts.
- **Resource Usage**: Each LightRAG instance requires its own resources (memory, CPU).
- **File Management**: Documents added to one repository are not automatically available in others.
- **Docker Container**: Each start/stop cycle creates and removes a Docker container named `lightrag-server`.

## Troubleshooting

- **Permission Issues**: If you encounter permission errors, ensure your user has write access to the specified directories.
- **Docker Volume Mounting**: If directories aren't properly mounted in Docker, check the Docker logs with `docker logs lightrag-server`.
- **Data Persistence**: All data is stored in the host directories and persists across container restarts.