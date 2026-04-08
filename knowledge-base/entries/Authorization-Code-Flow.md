---
aliases: [Auth Code Flow]
tags: [auth, flow]
status: formal
date: 2024-01-15
---
# Authorization-Code-Flow

The Authorization Code flow involves exchanging an authorization code for a token. This flow provides excellent security properties because the final [[Access-Token]] is never exposed to the user-agent (browser).

## Context
It is the standard mechanism in [[OAuth-2.0]] for confidential clients. Step one yields a temporary code, step two exchanges it directly via back-channel API call for the [[Access-Token]] and optionally a [[Refresh-Token]].

## Source
[[RFC-6749]]
