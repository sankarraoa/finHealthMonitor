/Users/sankar.amburkar/VSCode/finHealthMonitor/app/models/party.py:98: SAWarning: Implicitly combining column parties.tenant_id with column persons.tenant_id under attribute 'tenant_id'.  Please configure one or more attributes for these same-named columns explicitly.
  class Person(Party):
/Users/sankar.amburkar/VSCode/finHealthMonitor/app/models/party.py:98: SAWarning: Implicitly combining column parties.created_by with column persons.created_by under attribute 'created_by'.  Please configure one or more attributes for these same-named columns explicitly.
  class Person(Party):
/Users/sankar.amburkar/VSCode/finHealthMonitor/app/models/party.py:98: SAWarning: Implicitly combining column parties.modified_by with column persons.modified_by under attribute 'modified_by'.  Please configure one or more attributes for these same-named columns explicitly.
  class Person(Party):
/Users/sankar.amburkar/VSCode/finHealthMonitor/app/models/party.py:98: SAWarning: Implicitly combining column parties.created_at with column persons.created_at under attribute 'created_at'.  Please configure one or more attributes for these same-named columns explicitly.
  class Person(Party):
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Generating static SQL
INFO  [alembic.runtime.migration] Will assume transactional DDL.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INFO  [alembic.runtime.migration] Running upgrade  -> b350bf4bd660, Initial migration: create connections and tenants tables
-- Running upgrade  -> b350bf4bd660

CREATE TABLE connections (
    id VARCHAR NOT NULL, 
    category VARCHAR NOT NULL, 
    software VARCHAR NOT NULL, 
    name VARCHAR NOT NULL, 
    access_token TEXT NOT NULL, 
    refresh_token TEXT, 
    expires_in INTEGER, 
    token_created_at VARCHAR, 
    created_at VARCHAR NOT NULL, 
    updated_at VARCHAR NOT NULL, 
    extra_metadata JSON, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_connections_id ON connections (id);

CREATE INDEX ix_connections_software ON connections (software);

CREATE TABLE tenants (
    id VARCHAR NOT NULL, 
    connection_id VARCHAR NOT NULL, 
    tenant_id VARCHAR NOT NULL, 
    tenant_name VARCHAR NOT NULL, 
    xero_connection_id VARCHAR, 
    created_at VARCHAR NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(connection_id) REFERENCES connections (id) ON DELETE CASCADE
);

CREATE INDEX ix_tenants_connection_id ON tenants (connection_id);

CREATE INDEX ix_tenants_id ON tenants (id);

Traceback (most recent call last):
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/bin/alembic", line 8, in <module>
    sys.exit(main())
             ~~~~^^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/config.py", line 1047, in main
    CommandLine(prog=prog).main(argv=argv)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/config.py", line 1037, in main
    self.run_cmd(cfg, options)
    ~~~~~~~~~~~~^^^^^^^^^^^^^^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/config.py", line 971, in run_cmd
    fn(
    ~~^
        config,
        ^^^^^^^
        *[getattr(options, k, None) for k in positional],
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        **{k: getattr(options, k, None) for k in kwarg},
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/command.py", line 483, in upgrade
    script.run_env()
    ~~~~~~~~~~~~~~^^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/script/base.py", line 545, in run_env
    util.load_python_file(self.dir, "env.py")
    ~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/util/pyfiles.py", line 116, in load_python_file
    module = load_module_py(module_id, path)
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/util/pyfiles.py", line 136, in load_module_py
    spec.loader.exec_module(module)  # type: ignore
    ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^
  File "<frozen importlib._bootstrap_external>", line 1026, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/alembic/env.py", line 108, in <module>
    run_migrations_offline()
    ~~~~~~~~~~~~~~~~~~~~~~^^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/alembic/env.py", line 82, in run_migrations_offline
    context.run_migrations()
    ~~~~~~~~~~~~~~~~~~~~~~^^
  File "<string>", line 8, in run_migrations
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/runtime/environment.py", line 969, in run_migrations
    self.get_context().run_migrations(**kw)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/alembic/runtime/migration.py", line 626, in run_migrations
    step.migration_fn(**kw)
    ~~~~~~~~~~~~~~~~~^^^^^^
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/alembic/versions/b350bf4bd660_initial_migration_create_connections_.py", line 57, in upgrade
    inspector = inspect(bind)
  File "/Users/sankar.amburkar/VSCode/finHealthMonitor/venv/lib/python3.13/site-packages/sqlalchemy/inspection.py", line 147, in inspect
    raise exc.NoInspectionAvailable(
    ...<2 lines>...
    )
sqlalchemy.exc.NoInspectionAvailable: No inspection system is available for object of type <class 'sqlalchemy.engine.mock.MockConnection'>
