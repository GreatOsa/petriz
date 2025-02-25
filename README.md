# Petriz API Backend

This repository contains the FastAPI backend for the Petriz project.

Visit the API documentation at [http://localhost:8000/docs](http://localhost:8000/docs)

> The project structure may not follow conventional FastAPI project structures. This is because it uses pre-made utilities to speed-up and improve the development process, whilst adding some custom features.

## Quick Setup Guide

This project requires Python 3.10 or higher. To set up the project, follow these steps:

- Clone the repository
- Change into the project directory
  
  ```bash
    cd petriz
    ```

- Create and activate a virtual environment
  
  ```bash
    python -m venv venv && source venv/bin/activate
    ```

- Install `poetry` if you don't have it installed
  
  ```bash
    pip install poetry
    ```

- Install the project dependencies
  
  ```bash
    poetry install --no-dev
    ```

- Setup the environment variables
  
  ```bash
    cp .env.example .env // Update the values in the .env file
    ```

- Run the database migrations
  
  ```bash
    alembic upgrade head
    ```

- Load seed terms in `/slb_terms/` directory into the database
  
  ```bash
   chmod +x ./scripts/load_terms.sh && ./scripts/load_terms.sh ./slb_terms
    ```

> This step requires the `load_terms.sh` script to be executable. Also it might take a while to load all the terms into the database.

- Run the project
  
  ```bash
    uvicorn main:app --reload
    ```

- The project should now be running on `http://localhost:8000`

- Visit `core/settings.py` to update the project settings. You can learn more about the available settings and configurations by visiting the helpers submodule @ `helpers/fastapi/default_settings.py` and `helpers/fastapi/config.py`

- Check available commands with
  
  ```bash
    python main.py --help
    ```

- To access all API endpoints, you need internal API client credentials. You can run the following command to create one
  
  ```bash
    python main.py create_client --client_type internal
    ```
