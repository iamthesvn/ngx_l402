/// Why a Cashu token was not accepted. The variant carries the status.
#[derive(Debug)]
pub enum CashuError {
    /// Malformed, unparseable, or already spent — 401, as on the L402 path.
    BadCredential(String),
    /// A mint outside the list, wrong unit, too little value, missing lock —
    /// the cases NUT-24 answers 400.
    Unacceptable(String),
    /// Ours. Never 4xx: the swap may already have consumed the token, and
    /// calling it invalid invites the payer to discard money that was spent.
    Internal(String),
}

impl CashuError {
    pub fn http_status(&self) -> isize {
        match self {
            CashuError::BadCredential(_) => 401,
            CashuError::Unacceptable(_) => 400,
            CashuError::Internal(_) => 500,
        }
    }
}

impl std::fmt::Display for CashuError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CashuError::BadCredential(m)
            | CashuError::Unacceptable(m)
            | CashuError::Internal(m) => f.write_str(m),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bad_credential_is_401() {
        assert_eq!(
            CashuError::BadCredential("Failed to decode token".into()).http_status(),
            401
        );
    }

    #[test]
    fn unacceptable_is_400() {
        assert_eq!(
            CashuError::Unacceptable("Mint x not whitelisted".into()).http_status(),
            400
        );
    }

    /// The distinction that matters: our failures must not tell a payer their
    /// token was bad, because the swap may already have consumed it.
    #[test]
    fn internal_is_500_and_never_4xx() {
        let e = CashuError::Internal("mint receive failed: disk full".into());
        assert_eq!(e.http_status(), 500);
        assert!(!(400..500).contains(&e.http_status()));
    }

    #[test]
    fn display_yields_the_message_without_the_variant() {
        let e = CashuError::Unacceptable("Insufficient amount: 1000 < 1500".into());
        assert_eq!(e.to_string(), "Insufficient amount: 1000 < 1500");
    }

    /// Payer-fault variants stay in 4xx and ours stays in 5xx, whatever the
    /// message says — the property the string matching could not guarantee.
    #[test]
    fn payer_faults_are_4xx_and_ours_is_5xx() {
        let msg = "identical text";
        for e in [
            CashuError::BadCredential(msg.into()),
            CashuError::Unacceptable(msg.into()),
        ] {
            assert!((400..500).contains(&e.http_status()), "{e} should be 4xx");
        }
        assert!((500..600).contains(&CashuError::Internal(msg.into()).http_status()));
    }
}
