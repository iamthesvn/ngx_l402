//! Output-context escaping helpers (XSS / injection prevention).

/// Escape a string for safe interpolation into HTML text/attribute contexts.
pub fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}

/// Escape a string for safe interpolation into a JSON string literal, including
/// control characters. Used inside inline `<script>` JSON blobs to prevent
/// breaking out of the JSON/script context.
pub fn escape_json(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            // The HTML tokenizer ends a <script> element at the first literal
            // `</script`, whatever the JS string context, so `<` must not
            // survive. `>` and `&` are escaped too so the output is equally
            // safe if it is ever emitted into an HTML data context.
            '<' => out.push_str("\\u003c"),
            '>' => out.push_str("\\u003e"),
            '&' => out.push_str("\\u0026"),
            // Valid in JSON strings but line terminators in pre-ES2019 JS.
            '\u{2028}' => out.push_str("\\u2028"),
            '\u{2029}' => out.push_str("\\u2029"),
            c if (c as u32) < 0x20 => {
                use core::fmt::Write;
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn html_escapes_all_dangerous_chars() {
        assert_eq!(
            html_escape(r#"<a href="x" onclick='y'>&"#),
            "&lt;a href=&quot;x&quot; onclick=&#x27;y&#x27;&gt;&amp;"
        );
    }

    #[test]
    fn html_escape_leaves_safe_text() {
        assert_eq!(html_escape("hello world 123"), "hello world 123");
    }

    #[test]
    fn json_escapes_quotes_and_backslash() {
        assert_eq!(escape_json(r#"a"b\c"#), r#"a\"b\\c"#);
    }

    #[test]
    fn json_escapes_control_chars() {
        assert_eq!(escape_json("a\nb\tc\r"), "a\\nb\\tc\\r");
        // A control char < 0x20 (here 0x01) becomes .
        assert_eq!(escape_json("\u{0001}"), "\\u0001");
    }

    #[test]
    fn json_leaves_safe_text() {
        assert_eq!(escape_json("plain text 42"), "plain text 42");
    }

    #[test]
    fn json_escapes_script_context_breakout() {
        let out = escape_json("</script><img src=x onerror=alert(1)>");
        assert!(
            !out.to_ascii_lowercase().contains("</script"),
            "escape_json left a script-closing sequence intact: {}",
            out
        );
    }

    #[test]
    fn json_escapes_js_line_separators() {
        assert_eq!(escape_json("a\u{2028}b\u{2029}c"), "a\\u2028b\\u2029c");
    }
}
