main(): Unit {
 let escaped: String = "line\nquote: \""
 let block: String = """first
second"""
 println(escaped.concat(block))
}
