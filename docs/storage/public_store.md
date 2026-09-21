# Public project storage

`project_publications(user, project_id)` resolves the owner's publications,
including withdrawn versions, scoped by owner, tenant and private project.
The UI reuses an existing publication identity rather than creating a new link
for every update. Legacy projects with multiple links retain their association.

`set_visibility` changes only access, with ownership/tenant validation; it never
rewrites the published design or its immutable versions. Public getters,
version reads and cloning refuse withdrawn (`unpublished`) publications.
Unlisted designs remain accessible by link and absent from discovery.
Publishing and explicit updates still create immutable snapshots.

Both Firestore and in-memory implementations implement these contracts.
