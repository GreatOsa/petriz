# Petriz API Backend

FastAPI backend for the Petriz project.

Visit the API documentation on [Postman](https://documenter.getpostman.com/view/21622102/2sAYdeNCL5)

## Quick Setup using `uv`

This project requires Python 3.10 or higher. To set up the project, follow these steps:

To install `uv`, follow the instructions on the [uv documentation](https://docs.astral.sh/uv/getting-started/installation/)

- Clone the repository
- Change into the project directory
  
  ```bash
    cd petriz
    ```

- Synchronize the project dependencies
  
  ```bash
    uv sync
    ```

- Setup the environment variables
  
  ```bash
    cp .env.example .env // Update the values in the .env file
    ```

- Run database migrations
  
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
    uv run uvicorn main:app --reload
    ```

- The project should now be running on `http://localhost:8000`

- Visit `core/settings.py` to update the project settings. You can learn more about the available settings and configurations by visiting the helpers submodule @ `helpers/fastapi/default_settings.py` and `helpers/fastapi/config.py`

- Check available commands with
  
  ```bash
    uv run main.py --help
    ```

- To access all API endpoints, you need internal API client credentials. You can run the following command to create one
  
  ```bash
    uv run main.py create_client --client_type internal
    ```
