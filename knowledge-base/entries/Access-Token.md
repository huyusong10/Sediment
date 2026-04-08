---
aliases: [Access Token]
tags: [auth, credential]
status: formal
date: 2024-01-15
---
# Access-Token

An access token is a credential that can be used by an application to access an API. It represents the authorization of a specific application to access specific parts of a user's data.

## Context
Access tokens must be kept confidential in transit and in storage. They are the final output of the [[Authorization-Code-Flow]] in [[OAuth-2.0]], and they are often instantiated as a [[JWT]]. A short expiration time is recommended, relying on a [[Refresh-Token]] for continuity.

## Source
[[RFC-6749]]
