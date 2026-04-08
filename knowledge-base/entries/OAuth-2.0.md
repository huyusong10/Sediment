---
aliases: [OAuth2, Open Authorization 2.0]
tags: [auth, security]
status: formal
date: 2024-01-15
---
# OAuth-2.0

OAuth 2.0 is an authorization framework that enables a third-party application to obtain limited access to a HTTP service on behalf of a resource owner.

## Context
Instead of sharing credentials, the user authenticates with an identity provider, which issues an [[Access-Token]] to the client. This token is often formatted as a [[JWT|JSON Web Token]]. For secure web apps, the [[Authorization-Code-Flow]] is typically used.

## Source
[[RFC-6749]]
