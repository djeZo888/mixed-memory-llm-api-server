"""AST-extracted installed SGLang source; provenance.json records source hashes.

Do not hand-edit function bodies. Test collaborators are explicitly stubbed.
"""
from __future__ import annotations


async def get_server_info():
    """Get the server information (deprecated - use /server_info instead)."""
    logger.warning(
        "Endpoint '/get_server_info' is deprecated and will be removed in a future version. "
        "Please use '/server_info' instead."
    )
    return await server_info()


async def server_info():
    """Get the server information."""
    # Returns internal states per DP.
    internal_states: List[Dict[Any, Any]] = (
        await _global_state.tokenizer_manager.get_internal_state()
    )

    server_args = _global_state.tokenizer_manager.server_args

    # server_args.model_config is not serializable but should be excluded by asdict.
    return {
        **dataclasses.asdict(server_args),
        **_global_state.scheduler_info,
        "internal_states": internal_states,
        "version": __version__,
        # Structured KV-event publisher descriptor for KV-aware routers.
        # `None` when publishing is disabled or misconfigured; see
        # `ServerArgs.describe_kv_events_publisher` for the precise contract.
        "kv_events": server_args.describe_kv_events_publisher(),
    }


def _wait_and_warmup(
    server_args: ServerArgs,
    launch_callback: Optional[Callable[[], None]] = None,
    execute_warmup_func: Callable = _execute_server_warmup,
):
    if server_args.checkpoint_engine_wait_weights_before_ready:
        _wait_weights_ready()

    # Send a warmup request
    if not server_args.skip_server_warmup:
        if not execute_warmup_func(server_args):
            return
    else:
        _global_state.tokenizer_manager.server_status = ServerStatus.Up

    # The server is ready for requests
    logger.info("The server is fired up and ready to roll!")

    if server_args.delete_ckpt_after_loading:
        delete_directory(server_args.model_path)

    if server_args.debug_tensor_dump_input_file:
        kill_process_tree(os.getpid())

    if launch_callback is not None:
        launch_callback()


def _setup_and_run_http_server(
    server_args: ServerArgs,
    tokenizer_manager,
    template_manager,
    port_args: PortArgs,
    scheduler_infos: List[Dict],
    subprocess_watchdog: Optional[SubprocessWatchdog],
    execute_warmup_func: Callable = _execute_server_warmup,
    launch_callback: Optional[Callable[[], None]] = None,
):
    """Set up global state, configure middleware, and run uvicorn.

    Called by launch_server after subprocesses have been launched.
    """
    # Set global states
    set_global_state(
        _GlobalState(
            tokenizer_manager=tokenizer_manager,
            template_manager=template_manager,
            scheduler_info=scheduler_infos[0],
        )
    )

    # Store watchdog on tokenizer_manager (single source of truth for SIGQUIT handler)
    if tokenizer_manager is not None:
        tokenizer_manager._subprocess_watchdog = subprocess_watchdog

    if server_args.enable_metrics:
        add_prometheus_track_response_middleware(app)

    # Pass additional arguments to the lifespan function.
    # They will be used for additional initialization setups.
    if server_args.tokenizer_worker_num == 1:
        # If it is single tokenizer mode, we can pass the arguments by attributes of the app object.
        app.is_single_tokenizer_mode = True
        app.server_args = server_args
        app.warmup_thread_kwargs = dict(
            server_args=server_args,
            launch_callback=launch_callback,
            execute_warmup_func=execute_warmup_func,
        )

        # Add api key authorization
        # This is only supported in single tokenizer mode.
        #
        # Backward compatibility:
        # - api_key only: behavior matches legacy (all endpoints require api_key)
        # - no keys: legacy had no restriction; ADMIN_FORCE endpoints must still be rejected when
        #   admin_api_key is not configured.
        if (
            server_args.api_key
            or server_args.admin_api_key
            or app_has_admin_force_endpoints(app)
        ):
            from sglang.srt.utils.auth import add_api_key_middleware

            add_api_key_middleware(
                app,
                api_key=server_args.api_key,
                admin_api_key=server_args.admin_api_key,
            )
    else:
        # If it is multi-tokenizer mode, we need to write the arguments to shared memory
        # for other worker processes to read.
        app.is_single_tokenizer_mode = False
        multi_tokenizer_args_shm = write_data_for_multi_tokenizer(
            port_args, server_args, scheduler_infos[0]
        )

    try:
        # Update logging configs
        set_uvicorn_logging_configs(server_args)

        if server_args.ssl_certfile:
            logger.info(
                f"SSL enabled: certfile={server_args.ssl_certfile}, "
                f"keyfile={server_args.ssl_keyfile}"
            )

        # Listen for HTTP requests
        if server_args.tokenizer_worker_num == 1:
            if server_args.enable_http2:
                logger.info(
                    f"Starting embedded Granian HTTP/2 server on "
                    f"{server_args.host}:{server_args.port}"
                )
                _run_granian_server(
                    host=server_args.host,
                    port=server_args.port,
                    log_level=server_args.log_level_http or server_args.log_level,
                    ssl_certfile=server_args.ssl_certfile,
                    ssl_keyfile=server_args.ssl_keyfile,
                    ssl_ca_certs=server_args.ssl_ca_certs,
                    ssl_keyfile_password=server_args.ssl_keyfile_password,
                    ssl_verify=False,  # No MTLS supported for now.
                )
            elif server_args.enable_ssl_refresh:
                # Use Config/Server API for access to the SSLContext.
                config = uvicorn.Config(
                    app,
                    host=server_args.host,
                    port=server_args.port,
                    root_path=server_args.fastapi_root_path,
                    log_level=server_args.log_level_http or server_args.log_level,
                    timeout_keep_alive=envs.SGLANG_TIMEOUT_KEEP_ALIVE.get(),
                    loop="uvloop",
                    ssl_keyfile=server_args.ssl_keyfile,
                    ssl_certfile=server_args.ssl_certfile,
                    ssl_ca_certs=server_args.ssl_ca_certs,
                    ssl_keyfile_password=server_args.ssl_keyfile_password,
                )
                config.load()  # Creates the SSLContext

                from sglang.srt.entrypoints.ssl_utils import SSLCertRefresher

                server = uvicorn.Server(config)

                async def _run_with_ssl_refresh():
                    refresher = SSLCertRefresher(
                        config.ssl,
                        server_args.ssl_keyfile,
                        server_args.ssl_certfile,
                        server_args.ssl_ca_certs,
                    )
                    logger.info("SSL certificate auto-refresh enabled.")
                    try:
                        await server.serve()
                    finally:
                        refresher.stop()

                import asyncio

                asyncio.run(_run_with_ssl_refresh())
            else:
                # Default case, one tokenizer process
                uvicorn.run(
                    app,
                    host=server_args.host,
                    port=server_args.port,
                    root_path=server_args.fastapi_root_path,
                    log_level=server_args.log_level_http or server_args.log_level,
                    timeout_keep_alive=envs.SGLANG_TIMEOUT_KEEP_ALIVE.get(),
                    loop="uvloop",
                    ssl_keyfile=server_args.ssl_keyfile,
                    ssl_certfile=server_args.ssl_certfile,
                    ssl_ca_certs=server_args.ssl_ca_certs,
                    ssl_keyfile_password=server_args.ssl_keyfile_password,
                )
        else:
            # Multiple tokenizer and http processes
            from uvicorn.config import LOGGING_CONFIG

            LOGGING_CONFIG["loggers"]["sglang.srt.entrypoints.http_server"] = {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            }

            if server_args.enable_ssl_refresh:
                logger.warning(
                    "--enable-ssl-refresh is not supported with multiple "
                    "tokenizer workers (--tokenizer-worker-num > 1). "
                    "SSL refresh will be disabled."
                )

            if server_args.enable_http2:
                logger.info(
                    f"Starting embedded Granian HTTP/2 server on "
                    f"{server_args.host}:{server_args.port}"
                )
                _run_granian_server(
                    host=server_args.host,
                    port=server_args.port,
                    log_level=server_args.log_level_http or server_args.log_level,
                    tokenizer_worker_num=server_args.tokenizer_worker_num,
                    ssl_certfile=server_args.ssl_certfile,
                    ssl_keyfile=server_args.ssl_keyfile,
                    ssl_ca_certs=server_args.ssl_ca_certs,
                    ssl_keyfile_password=server_args.ssl_keyfile_password,
                )
            else:
                uvicorn.run(
                    "sglang.srt.entrypoints.http_server:app",
                    host=server_args.host,
                    port=server_args.port,
                    root_path=server_args.fastapi_root_path,
                    log_level=server_args.log_level_http or server_args.log_level,
                    timeout_keep_alive=envs.SGLANG_TIMEOUT_KEEP_ALIVE.get(),
                    timeout_worker_healthcheck=envs.SGLANG_UVICORN_WORKER_HEALTHCHECK_TIMEOUT.get(),
                    loop="uvloop",
                    workers=server_args.tokenizer_worker_num,
                    ssl_keyfile=server_args.ssl_keyfile,
                    ssl_certfile=server_args.ssl_certfile,
                    ssl_ca_certs=server_args.ssl_ca_certs,
                    ssl_keyfile_password=server_args.ssl_keyfile_password,
                )
    finally:
        if server_args.tokenizer_worker_num > 1:
            if multi_tokenizer_args_shm is not None:
                multi_tokenizer_args_shm.unlink()
            if _global_state is not None:
                _global_state.tokenizer_manager.socket_mapping.clear_all_sockets()


def launch_server(
    server_args: ServerArgs,
    init_tokenizer_manager_func: Callable = init_tokenizer_manager,
    run_scheduler_process_func: Callable = run_scheduler_process,
    run_detokenizer_process_func: Callable = run_detokenizer_process,
    execute_warmup_func: Callable = _execute_server_warmup,
    launch_callback: Optional[Callable[[], None]] = None,
):
    """
    Launch SRT (SGLang Runtime) Server.

    The SRT server consists of an HTTP server and an SRT engine.

    - HTTP server: A FastAPI server that routes requests to the engine.
    - The engine consists of three components:
        1. TokenizerManager: Tokenizes the requests and sends them to the scheduler.
        2. Scheduler (subprocess): Receives requests from the Tokenizer Manager, schedules batches, forwards them, and sends the output tokens to the Detokenizer Manager.
        3. DetokenizerManager (subprocess): Detokenizes the output tokens and sends the result back to the Tokenizer Manager.

    Note:
    1. The HTTP server, Engine, and TokenizerManager all run in the main process.
    2. Inter-process communication is done through IPC (each process uses a different port) via the ZMQ library.
    """
    # Launch subprocesses
    (
        tokenizer_manager,
        template_manager,
        port_args,
        scheduler_init_result,
        subprocess_watchdog,
    ) = Engine._launch_subprocesses(
        server_args=server_args,
        init_tokenizer_manager_func=init_tokenizer_manager_func,
        run_scheduler_process_func=run_scheduler_process_func,
        run_detokenizer_process_func=run_detokenizer_process_func,
    )

    _setup_and_run_http_server(
        server_args,
        tokenizer_manager,
        template_manager,
        port_args,
        scheduler_init_result.scheduler_infos,
        subprocess_watchdog,
        execute_warmup_func=execute_warmup_func,
        launch_callback=launch_callback,
    )
