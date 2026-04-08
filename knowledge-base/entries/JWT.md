---
aliases: [JSON Web Token]
tags: [auth, token-format]
status: formal
date: 2024-01-15
---
# JWT

JSON Web Token is a compact, URL-safe means of representing claims to be transferred between two parties. The claims in a JWT are encoded as a JSON object that is digitally signed using a JSON Web Signature.

## Context
When an [[OAuth-2.0]] server issues an [[Access-Token]], it frequently encodes it as a JWT so that the resource server can verify it statelessly.

## Source
[[RFC-7519]]
