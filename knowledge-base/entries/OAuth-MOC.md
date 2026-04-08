---
aliases: [OAuth Map of Content, OAuth Index]
tags: [auth, security, moc]
status: formal
date: 2024-01-15
---
# OAuth-MOC

This is a Map of Content (Hub node) for the [[OAuth-2.0|OAuth]] ecosystem. It organizes all the interconnected sub-concepts related to authentication and authorization.

## Core Concepts
- [[OAuth-2.0]]: The overall delegation framework.
- [[JWT]]: A popular format for representing the tokens safely.
- [[Access-Token]]: The actual credential used to access protected resources.

## Flows
- [[Authorization-Code-Flow]]: The most secure and recommended flow for confidential clients.
- [[Refresh-Token]]: Used to obtain a new [[Access-Token]] without re-prompting the user.
