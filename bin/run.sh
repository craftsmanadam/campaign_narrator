docker run --env-file ./.env.secrets --mount type=bind,source="$(pwd)/output_docker",target=/src/output craftsmanadam/${PROJECT_NAME}:latest
