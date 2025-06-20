from calendar import month_abbr
import os
import json
import datetime
from sqlalchemy.orm import Session
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob.aio import BlobServiceClient
from api.v1.repository.project_repository import (
    filter_projects_by_name,
    get_projects_by_enterprise,
    get_visible_projects_for_students,
    list_projects_by_enterprise,
    save_project_to_sql,
    get_all_projects,
    get_project_by_id,
    update_project,
    delete_project,
    update_project_status
)
from api.v1.schemas.project_schema import ProjectResponse



AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)

async def load_requirements_from_blob(blob_path: str) -> str:
    try:
        blob_full_path = f"{blob_path}/requirements.html"
        blob_client = blob_service_client.get_blob_client(container="projects", blob=blob_full_path)

        # ✅ Use `await` com download_blob
        stream = await blob_client.download_blob()
        content = await stream.readall()
        return content.decode("utf-8")
    except Exception as e:
        print("Erro ao carregar blob:", e)
        return ""
    
async def publish_project_service(db: Session, data):
    connection_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    async with BlobServiceClient.from_connection_string(connection_str) as blob_service_client:
        container_client = blob_service_client.get_container_client("projects")

        # Attempt to create the container if it doesn't exist
        try:
            await container_client.create_container()
        except ResourceExistsError:
            pass  # Container already exists

        # Unique path for project assets
        timestamp = datetime.datetime.utcnow().isoformat().replace(":", "-")
        path_prefix = f"{data.enterprise_id}/{data.project_name}_{timestamp}"

        # Upload files to Azure Blob Storage
        await container_client.upload_blob(
            name=f"{path_prefix}/requirements.html",
            data=data.requirements_html,
            overwrite=True
        )
        await container_client.upload_blob(
            name=f"{path_prefix}/menus.json",
            data=json.dumps(data.menus),
            overwrite=True
        )
        await container_client.upload_blob(
            name=f"{path_prefix}/deliverables.json",
            data=json.dumps(data.deliverables),
            overwrite=True
        )

    # Save project metadata and structure to SQL database
    await save_project_to_sql(
        db,
        project_name=data.project_name,
        deliverables=data.deliverables,
        enterprise_id=data.enterprise_id,
        blob_path=path_prefix,
        description=data.description,
        technologies=data.technologies,
        complexity=data.complexity,
        category=data.category,
        score=data.score,
        country=data.country
    )

    return path_prefix

# Retorna todos os projetos
async def list_projects_service(db: Session):
    return await get_all_projects(db)

# Retorna um projeto por ID
async def get_project_service(db: Session, project_id: int):
    return await get_project_by_id(db, project_id)

# Atualiza um projeto
async def update_project_service(db: Session, project_id: int, update_data: dict):
    return await update_project(db, project_id, update_data)

# Deleta um projeto
async def delete_project_service(db: Session, project_id: int):
    return await delete_project(db, project_id)

async def list_enterprise_projects(db: Session, enterprise_id: str) -> list[ProjectResponse]:
    projects = get_projects_by_enterprise(db, enterprise_id)
    responses = []
    
    for project in projects:
        requirements = await load_requirements_from_blob(project.blob_path) if project.blob_path else {}

        responses.append(ProjectResponse(
            id=project.id,
            name=project.name,
            enterprise_id=project.enterprise_id,
            created_at=project.created_at,
            deliverables=project.deliverables,
            description=project.description,
            technologies=project.technologies,
            complexity=project.complexity,
            category=project.category,
            score=project.score,
            country=project.country,
            status=project.status,
            progress=project.progress,
            team=project.students,
            requirements=requirements
        ))

    return responses

def get_filtered_projects(db: Session, name: str):
    return filter_projects_by_name(db, name)

async def update_project_status_service(db: Session, project_id: str, new_status: str):
    return update_project_status(db, project_id, new_status)

def list_visible_projects(db: Session):
    projects = get_visible_projects_for_students(db)

    def serialize(project):
        estimated_hours = sum(
            task.estimated_time
            for deliverable in project.deliverables
            for task in deliverable.tasks
        )
        return {
            "id": project.id,
            "name": project.name,
            "enterprise_id": project.enterprise_id,
            "enterprise_name": project.owner.name,
            "description": project.description,
            "complexity": project.complexity,
            "score": project.score,
            "status": project.status,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "blob_path": project.blob_path,
            "technologies": project.technologies,
            "category": project.category,
            "country": project.country,
            "estimated_hours": estimated_hours,
        }

    return [serialize(p) for p in projects]

async def list_projects_by_enterprise_service(db: Session, enterprise_id: str):
    return list_projects_by_enterprise(db, enterprise_id)