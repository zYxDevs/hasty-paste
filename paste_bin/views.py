from datetime import datetime
from functools import wraps
from quart import (Blueprint, abort, make_response, redirect, render_template,
                   request, send_file, url_for)
from quart_schema import hide_route, validate_request, validate_response

from . import helpers
from .config import get_settings

front_end = Blueprint("front_end", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


def handle_paste_exceptions(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except helpers.PasteException:
            abort(404)
    return wrapper


@front_end.get("/")
@hide_route
async def get_index():
    return await render_template("index.jinja")


@front_end.get("/new")
@hide_route
async def get_new_paste():
    return await render_template("new.jinja")


@front_end.post("/new")
@hide_route
async def post_new_paste():
    form = await request.form

    paste_content = form["paste-content"].replace("\r\n", "\n")
    expires_at = form.get("expires-at", None, helpers.get_form_datetime)
    long_id = form.get("long-id", False, bool)

    paste_meta = helpers.PasteMeta(
        paste_id=helpers.create_paste_id(long_id),
        creation_dt=datetime.utcnow(),
        expire_dt=expires_at,
    )

    root_path = get_settings().PASTE_ROOT
    paste_path = helpers.create_paste_path(root_path, paste_meta.paste_id, True)

    await helpers.write_paste(paste_path, paste_meta, paste_content.encode())

    return redirect(url_for(".get_view_paste", paste_id=paste_meta.paste_id))


@front_end.get("/<paste_id>")
@hide_route
@handle_paste_exceptions
async def get_view_paste(paste_id: str):
    root_path = get_settings().PASTE_ROOT
    paste_path = helpers.create_paste_path(root_path, paste_id)

    if not paste_path.is_file():
        abort(404)

    paste_meta = await helpers.read_paste_meta(paste_path)

    if paste_meta.is_expired:
        paste_path.unlink(True)
        abort(404)

    content = helpers.read_paste_content(paste_path)

    return await render_template(
        "view.jinja",
        paste_content=content,
        meta=paste_meta,
    )


@front_end.get("/<paste_id>/raw")
@hide_route
@handle_paste_exceptions
async def get_raw_paste(paste_id: str):
    root_path = get_settings().PASTE_ROOT
    paste_path = helpers.create_paste_path(root_path, paste_id)

    if not paste_path.is_file():
        abort(404)

    paste_meta = await helpers.read_paste_meta(paste_path)

    if paste_meta.is_expired:
        paste_path.unlink(True)
        abort(404)

    content = helpers.read_paste_content(paste_path)

    response = await make_response(content)
    response.mimetype="text/plain"

    return response


@api.post("/pastes")
@validate_request(helpers.PasteMetaCreate)
@validate_response(helpers.PasteMeta)
async def post_api_paste_new(data: helpers.PasteMetaCreate):
    """
    Create a new paste
    """
    paste_meta = helpers.PasteMeta(
        paste_id=helpers.create_paste_id(data.long_id),
        creation_dt=datetime.utcnow(),
        expire_dt=data.expire_dt,
    )

    root_path = get_settings().PASTE_ROOT
    paste_path = helpers.create_paste_path(root_path, paste_meta.paste_id, True)

    await helpers.write_paste(paste_path, paste_meta, data.content)
    return paste_meta


@api.get("/pastes/<paste_id>")
@handle_paste_exceptions
async def get_api_paste_raw(paste_id: str):
    """
    Get the paste raw file, if one exists
    """
    root_path = get_settings().PASTE_ROOT
    paste_path = helpers.create_paste_path(root_path, paste_id)

    if not paste_path.is_file():
        abort(404)

    paste_meta = await helpers.read_paste_meta(paste_path)

    if paste_meta.is_expired:
        paste_path.unlink(True)
        abort(404)

    return await send_file(paste_path)


@api.get("/pastes/<paste_id>/meta")
@validate_response(helpers.PasteMeta)
@handle_paste_exceptions
async def get_api_paste_meta(paste_id: str):
    """
    Get the paste meta, if one exists
    """
    root_path = get_settings().PASTE_ROOT
    paste_path = helpers.create_paste_path(root_path, paste_id)

    if not paste_path.is_file():
        abort(404)

    paste_meta = await helpers.read_paste_meta(paste_path)

    if paste_meta.is_expired:
        paste_path.unlink(True)
        abort(404)

    return paste_meta


@api.get("/pastes/<paste_id>/content")
@handle_paste_exceptions
async def get_api_paste_content(paste_id: str):
    """
    Get the paste content, if one exists
    """
    root_path = get_settings().PASTE_ROOT
    paste_path = helpers.create_paste_path(root_path, paste_id)

    if not paste_path.is_file():
        abort(404)

    paste_meta = await helpers.read_paste_meta(paste_path)

    if paste_meta.is_expired:
        paste_path.unlink(True)
        abort(404)

    content = helpers.read_paste_content(paste_path)

    response = await make_response(content)
    response.mimetype="text/plain"

    return response
