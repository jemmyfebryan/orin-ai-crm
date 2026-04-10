"""
Test that image URLs are filtered out from final messages.

This test verifies that when the agent sends product images via API,
the image URLs are not included in the text response.
"""

import pytest
from src.orin_ai_crm.core.agents.nodes.quality_check_nodes import filter_final_messages


class TestFilterImageUrls:
    """Test image URL filtering in final messages"""

    def test_filter_single_image_url(self):
        """Test that a single image URL is removed from messages"""
        messages = [
            "Ini dia gambar produk OBU V untuk Kak Jemmy. 😊",
            "https://ai.orin.id/public/products/product_2.png",
            "Ada lagi yang bisa SiOrin bantu? 🙏"
        ]

        filtered = filter_final_messages(messages)

        # Should only have 2 messages (image URL removed)
        assert len(filtered) == 2
        assert filtered[0] == "Ini dia gambar produk OBU V untuk Kak Jemmy. 😊"
        assert filtered[1] == "Ada lagi yang bisa SiOrin bantu? 🙏"

    def test_filter_multiple_image_urls(self):
        """Test that multiple image URLs are removed"""
        messages = [
            "Berikut beberapa gambar produk:",
            "https://ai.orin.id/public/products/product_1.png",
            "https://ai.orin.id/public/products/product_2.jpg",
            "Semoga cocok dengan kebutuhan Kakak! 😊"
        ]

        filtered = filter_final_messages(messages)

        # Should only have 2 messages (both image URLs removed)
        assert len(filtered) == 2
        assert filtered[0] == "Berikut beberapa gambar produk:"
        assert filtered[1] == "Semoga cocok dengan kebutuhan Kakak! 😊"

    def test_filter_image_url_with_query_params(self):
        """Test that image URLs with query parameters are removed"""
        messages = [
            "Ini gambarnya kak",
            "https://ai.orin.id/public/products/product_3.png?v=1&size=large",
            "Terima kasih"
        ]

        filtered = filter_final_messages(messages)

        # Should only have 2 messages
        assert len(filtered) == 2
        assert "https://" not in str(filtered)
        assert filtered[0] == "Ini gambarnya kak"
        assert filtered[1] == "Terima kasih"

    def test_filter_image_url_within_text(self):
        """Test that image URLs within text lines are removed"""
        messages = [
            "Ini gambar produknya: https://ai.orin.id/public/products/product_4.png semoga bermanfaat!"
        ]

        filtered = filter_final_messages(messages)

        # Should have 1 message with URL removed
        assert len(filtered) == 1
        assert "https://" not in filtered[0]
        assert "Ini gambar produknya:" in filtered[0]
        assert "semoga bermanfaat!" in filtered[0]

    def test_preserve_non_image_urls(self):
        """Test that non-image URLs are preserved (e.g., website links)"""
        messages = [
            "Berikut info produk kami",
            "Kunjungi website kami di https://orin.id untuk info lebih lanjut",
            "Terima kasih"
        ]

        filtered = filter_final_messages(messages)

        # Should have all 3 messages (website URL preserved)
        assert len(filtered) == 3
        assert "https://orin.id" in filtered[1]

    def test_preserve_non_url_messages(self):
        """Test that regular messages without URLs are unchanged"""
        messages = [
            "Halo kak, ada yang bisa saya bantu?",
            "Kakak bisa lihat katalog produk kami",
            "Terima kasih telah menghubungi ORIN GPS Tracker 🙏"
        ]

        filtered = filter_final_messages(messages)

        # Should have all 3 messages unchanged
        assert len(filtered) == 3
        assert filtered == messages

    def test_filter_various_image_extensions(self):
        """Test that various image file extensions are filtered"""
        messages = [
            "https://example.com/image.png",
            "https://example.com/photo.jpg",
            "https://example.com/pic.jpeg",
            "https://example.com/graphic.gif",
            "https://example.com/picture.webp",
            "Regular message here"
        ]

        filtered = filter_final_messages(messages)

        # Should only have 1 message (all image URLs removed)
        assert len(filtered) == 1
        assert filtered[0] == "Regular message here"

    def test_exclamation_mark_filter_still_works(self):
        """Test that exclamation mark filter still works alongside image URL filter"""
        messages = [
            "Halo kak Jemmy! Ada yang bisa saya bantu?",
            "https://ai.orin.id/public/products/product_5.png",
            "Terima kasih!"
        ]

        filtered = filter_final_messages(messages, customer_name="Jemmy")

        # Should have 2 messages with both filters applied
        assert len(filtered) == 2
        # Exclamation mark after name should be replaced with comma
        assert "Jemmy," in filtered[0]
        assert "Jemmy!" not in filtered[0]
        # Image URL should be removed
        assert "https://" not in str(filtered)

    def test_empty_messages_after_filtering(self):
        """Test that messages that become empty after filtering are removed"""
        messages = [
            "Some text here",
            "https://ai.orin.id/public/products/product_6.png",  # This will be removed entirely
            "More text"
        ]

        filtered = filter_final_messages(messages)

        # Should only have 2 messages (empty message removed)
        assert len(filtered) == 2
        assert filtered[0] == "Some text here"
        assert filtered[1] == "More text"

    def test_empty_input(self):
        """Test that empty input is handled correctly"""
        filtered = filter_final_messages([])
        assert filtered == []

    def test_none_input(self):
        """Test that None input is handled correctly"""
        filtered = filter_final_messages(None)
        assert filtered == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
